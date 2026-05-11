#!/usr/bin/env python3
"""
Databricks Telemetry Generator
Simulates realistic Databricks metrics, logs, and traces for observability testing
"""

import os
import time
import random
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import uuid

import requests
import redis
import psycopg2
from kafka import KafkaProducer
from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram, push_to_gateway
from opentelemetry import trace, metrics, baggage, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagator.b3 import B3MultiFormat
from faker import Faker
import structlog

# Configuration
@dataclass
class Config:
    prometheus_gateway: str = os.getenv("PROMETHEUS_GATEWAY", "http://pushgateway:9091")
    loki_endpoint: str = os.getenv("LOKI_ENDPOINT", "http://loki:3100/loki/api/v1/push")
    tempo_endpoint: str = os.getenv("TEMPO_ENDPOINT", "http://tempo:4317")
    kafka_brokers: str = os.getenv("KAFKA_BROKERS", "kafka:9092")
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_db: str = os.getenv("POSTGRES_DB", "databricks_observability")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres123")
    generation_interval: int = int(os.getenv("GENERATION_INTERVAL", "5"))
    failure_rate: float = float(os.getenv("FAILURE_RATE", "0.1"))

# Initialize logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Initialize Faker
fake = Faker()

class DatabricksTelemetryGenerator:
    def __init__(self, config: Config):
        self.config = config
        self.registry = CollectorRegistry()
        self.faker = Faker()
        
        # Initialize OpenTelemetry
        self._setup_opentelemetry()
        
        # Initialize metrics
        self._setup_metrics()
        
        # Initialize connections
        self._setup_connections()
        
        # Generate sample data
        self.workspaces = self._generate_workspaces()
        self.clusters = self._generate_clusters()
        self.jobs = self._generate_jobs()
        self.notebooks = self._generate_notebooks()
        self.pipelines = self._generate_pipelines()
        self.warehouses = self._generate_warehouses()
        
        logger.info("Databricks Telemetry Generator initialized", 
                   workspaces=len(self.workspaces),
                   clusters=len(self.clusters),
                   jobs=len(self.jobs))

    def _setup_opentelemetry(self):
        """Setup OpenTelemetry tracing and metrics"""
        # Set up tracing
        trace.set_tracer_provider(TracerProvider())
        tracer_provider = trace.get_tracer_provider()
        span_processor = BatchSpanProcessor(
            OTLPSpanExporter(endpoint=self.config.tempo_endpoint, insecure=True)
        )
        tracer_provider.add_span_processor(span_processor)
        
        # Set up metrics
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=self.config.tempo_endpoint, insecure=True),
            export_interval_millis=15000,
        )
        metrics.set_meter_provider(MeterProvider(metric_reader=metric_reader))
        
        # Set up propagation
        set_global_textmap(B3MultiFormat())
        
        # Instrument libraries
        RequestsInstrumentor().instrument()
        LoggingInstrumentor().instrument()
        
        self.tracer = trace.get_tracer(__name__)
        self.meter = metrics.get_meter(__name__)

    def _setup_metrics(self):
        """Setup Prometheus metrics"""
        # Cluster metrics
        self.cluster_up = Gauge('databricks_cluster_up', 'Cluster status', 
                               ['workspace', 'cluster_id', 'cluster_name', 'environment'], registry=self.registry)
        self.cluster_cpu_usage = Gauge('databricks_cluster_cpu_usage_percent', 'CPU usage percentage',
                                      ['workspace', 'cluster_id', 'cluster_name'], registry=self.registry)
        self.cluster_memory_usage = Gauge('databricks_cluster_memory_usage_percent', 'Memory usage percentage',
                                         ['workspace', 'cluster_id', 'cluster_name'], registry=self.registry)
        self.cluster_executor_failures = Counter('databricks_cluster_executor_failures_total', 'Executor failures',
                                                 ['workspace', 'cluster_id', 'cluster_name'], registry=self.registry)
        self.cluster_cost = Gauge('databricks_cluster_cost_per_hour', 'Cost per hour',
                                 ['workspace', 'cluster_id', 'cluster_name', 'instance_type'], registry=self.registry)
        self.cluster_idle_time = Gauge('databricks_cluster_idle_time_seconds', 'Idle time',
                                     ['workspace', 'cluster_id', 'cluster_name'], registry=self.registry)
        
        # Job metrics
        self.job_failed = Gauge('databricks_job_failed', 'Job failure status',
                               ['workspace', 'job_id', 'job_name', 'run_id'], registry=self.registry)
        self.job_duration = Histogram('databricks_job_duration_seconds', 'Job duration',
                                     ['workspace', 'job_id', 'job_name'], registry=self.registry)
        self.job_queue_time = Gauge('databricks_job_queue_time_seconds', 'Queue time',
                                   ['workspace', 'job_id', 'job_name'], registry=self.registry)
        
        # Pipeline metrics
        self.pipeline_failed = Gauge('databricks_pipeline_failed', 'Pipeline failure status',
                                   ['workspace', 'pipeline_name', 'pipeline_id'], registry=self.registry)
        self.streaming_lag = Gauge('databricks_streaming_lag_seconds', 'Streaming lag',
                                  ['workspace', 'pipeline_name', 'stream_name'], registry=self.registry)
        self.delta_latency = Gauge('databricks_delta_table_latency_seconds', 'Delta table latency',
                                  ['workspace', 'table_name', 'pipeline_name'], registry=self.registry)
        
        # SQL Warehouse metrics
        self.sql_warehouse_up = Gauge('databricks_sql_warehouse_up', 'SQL Warehouse status',
                                     ['workspace', 'warehouse_id', 'warehouse_name'], registry=self.registry)
        self.sql_query_failures = Counter('databricks_sql_query_failures_total', 'SQL query failures',
                                         ['workspace', 'warehouse_id', 'warehouse_name'], registry=self.registry)
        self.sql_query_duration = Histogram('databricks_sql_query_duration_seconds', 'SQL query duration',
                                           ['workspace', 'warehouse_id', 'warehouse_name'], registry=self.registry)
        
        # DBFS metrics
        self.dbfs_errors = Counter('databricks_dbfs_errors_total', 'DBFS errors',
                                  ['workspace', 'operation', 'path'], registry=self.registry)
        self.dbfs_usage = Gauge('databricks_dbfs_usage_percent', 'DBFS usage percentage',
                               ['workspace', 'mount_point'], registry=self.registry)
        
        # Unity Catalog metrics
        self.unity_catalog_access_denied = Counter('databricks_unity_catalog_access_denied_total', 'Access denied',
                                                  ['workspace', 'catalog', 'schema', 'user'], registry=self.registry)
        self.unity_catalog_query_duration = Histogram('databricks_unity_catalog_query_duration_seconds', 'Query duration',
                                                     ['workspace', 'catalog', 'schema'], registry=self.registry)
        
        # Spark metrics
        self.spark_task_failed = Counter('spark_task_failed_total', 'Failed tasks',
                                        ['workspace', 'application_id', 'stage_id'], registry=self.registry)
        self.spark_stage_failed = Counter('spark_stage_failed_total', 'Failed stages',
                                          ['workspace', 'application_id'], registry=self.registry)
        self.spark_gc_time = Gauge('spark_gc_time_percent', 'GC time percentage',
                                  ['workspace', 'application_id', 'executor_id'], registry=self.registry)
        
        # SLO metrics
        self.slo_burn_rate = Gauge('databricks_job_slo_burn_rate', 'SLO burn rate',
                                  ['workspace', 'slo_name', 'service'], registry=self.registry)
        self.error_budget_remaining = Gauge('databricks_error_budget_remaining_percent', 'Error budget remaining',
                                           ['workspace', 'slo_name', 'service'], registry=self.registry)

    def _setup_connections(self):
        """Setup external connections"""
        try:
            # Redis connection
            self.redis_client = redis.Redis(host=self.config.redis_host, port=6379, decode_responses=True)
            self.redis_client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            self.redis_client = None
        
        try:
            # Kafka producer
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=self.config.kafka_brokers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            logger.info("Connected to Kafka")
        except Exception as e:
            logger.error("Failed to connect to Kafka", error=str(e))
            self.kafka_producer = None
        
        try:
            # PostgreSQL connection
            self.postgres_conn = psycopg2.connect(
                host=self.config.postgres_host,
                database=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password
            )
            logger.info("Connected to PostgreSQL")
        except Exception as e:
            logger.error("Failed to connect to PostgreSQL", error=str(e))
            self.postgres_conn = None

    def _generate_workspaces(self) -> List[Dict]:
        """Generate sample workspaces"""
        workspaces = []
        for i in range(3):
            workspace = {
                'id': f"ws-{fake.uuid4()[:8]}",
                'name': f"Workspace-{i+1}",
                'environment': random.choice(['prod', 'staging', 'dev']),
                'region': random.choice(['us-west-2', 'us-east-1', 'eu-west-1']),
                'team': random.choice(['data-platform', 'ml-team', 'analytics', 'engineering'])
            }
            workspaces.append(workspace)
        return workspaces

    def _generate_clusters(self) -> List[Dict]:
        """Generate sample clusters"""
        clusters = []
        instance_types = ['i3.xlarge', 'i3.2xlarge', 'i3.4xlarge', 'r5.xlarge', 'r5.2xlarge']
        
        for i in range(8):
            workspace = random.choice(self.workspaces)
            cluster = {
                'id': f"cluster-{fake.uuid4()[:8]}",
                'name': f"Cluster-{i+1}",
                'workspace': workspace['id'],
                'workspace_name': workspace['name'],
                'environment': workspace['environment'],
                'team': workspace['team'],
                'instance_type': random.choice(instance_types),
                'num_workers': random.randint(2, 10),
                'spark_version': f"3.{random.randint(3, 4)}.{random.randint(0, 2)}",
                'autotermination_minutes': random.randint(10, 120),
                'status': random.choice(['Running', 'Terminated', 'Pending', 'Resizing']),
                'created_time': fake.date_time_between(start_date='-30d', end_date='now'),
                'last_activity': fake.date_time_between(start_date='-1d', end_date='now')
            }
            clusters.append(cluster)
        return clusters

    def _generate_jobs(self) -> List[Dict]:
        """Generate sample jobs"""
        jobs = []
        job_types = ['spark', 'python', 'sql', 'jar', 'notebook']
        
        for i in range(15):
            workspace = random.choice(self.workspaces)
            job = {
                'id': f"job-{fake.uuid4()[:8]}",
                'name': f"Job-{i+1}",
                'workspace': workspace['id'],
                'workspace_name': workspace['name'],
                'environment': workspace['environment'],
                'team': workspace['team'],
                'job_type': random.choice(job_types),
                'schedule': random.choice(['0 2 * * *', '0 6 * * *', '0 10,14,18 * * *', '*/30 * * * *']),
                'max_concurrent_runs': random.randint(1, 5),
                'timeout_seconds': random.randint(3600, 14400),
                'last_run_id': fake.uuid4()[:8],
                'last_run_status': random.choice(['SUCCEEDED', 'FAILED', 'RUNNING', 'PENDING']),
                'last_run_time': fake.date_time_between(start_date='-1d', end_date='now')
            }
            jobs.append(job)
        return jobs

    def _generate_notebooks(self) -> List[Dict]:
        """Generate sample notebooks"""
        notebooks = []
        
        for i in range(20):
            workspace = random.choice(self.workspaces)
            notebook = {
                'id': f"notebook-{fake.uuid4()[:8]}",
                'name': f"Notebook-{i+1}",
                'workspace': workspace['id'],
                'workspace_name': workspace['name'],
                'environment': workspace['environment'],
                'team': workspace['team'],
                'language': random.choice(['python', 'scala', 'sql', 'r']),
                'path': f"/{workspace['team']}/{'/'.join(fake.words(nb=3))}",
                'created_time': fake.date_time_between(start_date='-30d', end_date='now'),
                'last_modified': fake.date_time_between(start_date='-7d', end_date='now'),
                'clusters_used': random.sample([c['id'] for c in self.clusters], random.randint(1, 3))
            }
            notebooks.append(notebook)
        return notebooks

    def _generate_pipelines(self) -> List[Dict]:
        """Generate sample Delta Live Tables pipelines"""
        pipelines = []
        
        for i in range(10):
            workspace = random.choice(self.workspaces)
            pipeline = {
                'id': f"pipeline-{fake.uuid4()[:8]}",
                'name': f"Pipeline-{i+1}",
                'workspace': workspace['id'],
                'workspace_name': workspace['name'],
                'environment': workspace['environment'],
                'team': workspace['team'],
                'pipeline_type': random.choice(['streaming', 'batch']),
                'target_schema': f"{workspace['team']}_target",
                'continuous': random.choice([True, False]),
                'development': random.choice([True, False]),
                'last_update': fake.date_time_between(start_date='-1d', end_date='now'),
                'status': random.choice(['UPDATING', 'ACTIVE', 'FAILED', 'IDLE'])
            }
            pipelines.append(pipeline)
        return pipelines

    def _generate_warehouses(self) -> List[Dict]:
        """Generate sample SQL warehouses"""
        warehouses = []
        warehouse_types = ['PRO', 'SERVERLESS']
        
        for i in range(6):
            workspace = random.choice(self.workspaces)
            warehouse = {
                'id': f"warehouse-{fake.uuid4()[:8]}",
                'name': f"Warehouse-{i+1}",
                'workspace': workspace['id'],
                'workspace_name': workspace['name'],
                'environment': workspace['environment'],
                'team': workspace['team'],
                'warehouse_type': random.choice(warehouse_types),
                'size': random.choice(['Small', 'Medium', 'Large', 'X-Large']),
                'max_num_clusters': random.randint(1, 8),
                'auto_stop_mins': random.randint(10, 60),
                'status': random.choice(['RUNNING', 'STOPPING', 'STOPPED'])
            }
            warehouses.append(warehouse)
        return warehouses

    def generate_cluster_metrics(self):
        """Generate cluster-related metrics"""
        with self.tracer.start_as_current_span("generate_cluster_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            for cluster in self.clusters:
                # Simulate cluster status changes
                is_up = random.random() > 0.05  # 95% uptime
                self.cluster_up.labels(
                    workspace=cluster['workspace_name'],
                    cluster_id=cluster['id'],
                    cluster_name=cluster['name'],
                    environment=cluster['environment']
                ).set(1 if is_up else 0)
                
                if is_up:
                    # CPU and memory usage
                    cpu_usage = random.gauss(60, 20)
                    cpu_usage = max(0, min(100, cpu_usage))
                    self.cluster_cpu_usage.labels(
                        workspace=cluster['workspace_name'],
                        cluster_id=cluster['id'],
                        cluster_name=cluster['name']
                    ).set(cpu_usage)
                    
                    memory_usage = random.gauss(70, 15)
                    memory_usage = max(0, min(100, memory_usage))
                    self.cluster_memory_usage.labels(
                        workspace=cluster['workspace_name'],
                        cluster_id=cluster['id'],
                        cluster_name=cluster['name']
                    ).set(memory_usage)
                    
                    # Random executor failures
                    if random.random() < self.config.failure_rate:
                        failures = random.randint(1, 5)
                        self.cluster_executor_failures.labels(
                            workspace=cluster['workspace_name'],
                            cluster_id=cluster['id'],
                            cluster_name=cluster['name']
                        )._value._value += failures
                    
                    # Cost calculation (simplified)
                    cost_per_hour = {
                        'i3.xlarge': 0.5,
                        'i3.2xlarge': 1.0,
                        'i3.4xlarge': 2.0,
                        'r5.xlarge': 0.6,
                        'r5.2xlarge': 1.2
                    }
                    total_cost = cost_per_hour.get(cluster['instance_type'], 1.0) * (cluster['num_workers'] + 1)
                    self.cluster_cost.labels(
                        workspace=cluster['workspace_name'],
                        cluster_id=cluster['id'],
                        cluster_name=cluster['name'],
                        instance_type=cluster['instance_type']
                    ).set(total_cost)
                    
                    # Idle time
                    idle_time = random.randint(0, 3600)
                    self.cluster_idle_time.labels(
                        workspace=cluster['workspace_name'],
                        cluster_id=cluster['id'],
                        cluster_name=cluster['name']
                    ).set(idle_time)

    def generate_job_metrics(self):
        """Generate job-related metrics"""
        with self.tracer.start_as_current_span("generate_job_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            for job in self.jobs:
                # Simulate job failures
                job_failed = random.random() < self.config.failure_rate
                self.job_failed.labels(
                    workspace=job['workspace_name'],
                    job_id=job['id'],
                    job_name=job['name'],
                    run_id=job['last_run_id']
                ).set(1 if job_failed else 0)
                
                # Job duration
                duration = random.gauss(300, 120)  # 5 minutes average
                duration = max(10, min(7200, duration))  # 10 seconds to 2 hours
                self.job_duration.labels(
                    workspace=job['workspace_name'],
                    job_id=job['id'],
                    job_name=job['name']
                ).observe(duration)
                
                # Queue time
                queue_time = random.gauss(60, 30)
                queue_time = max(0, min(600, queue_time))  # 0 to 10 minutes
                self.job_queue_time.labels(
                    workspace=job['workspace_name'],
                    job_id=job['id'],
                    job_name=job['name']
                ).set(queue_time)

    def generate_pipeline_metrics(self):
        """Generate pipeline metrics"""
        with self.tracer.start_as_current_span("generate_pipeline_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            for pipeline in self.pipelines:
                # Pipeline failures
                pipeline_failed = random.random() < self.config.failure_rate * 0.5
                self.pipeline_failed.labels(
                    workspace=pipeline['workspace_name'],
                    pipeline_name=pipeline['name'],
                    pipeline_id=pipeline['id']
                ).set(1 if pipeline_failed else 0)
                
                # Streaming lag (for streaming pipelines)
                if pipeline['pipeline_type'] == 'streaming':
                    lag = random.gauss(30, 15)
                    lag = max(0, min(300, lag))  # 0 to 5 minutes
                    self.streaming_lag.labels(
                        workspace=pipeline['workspace_name'],
                        pipeline_name=pipeline['name'],
                        stream_name=f"stream_{fake.word()}"
                    ).set(lag)
                
                # Delta table latency
                latency = random.gauss(120, 60)
                latency = max(10, min(600, latency))  # 10 seconds to 10 minutes
                self.delta_latency.labels(
                    workspace=pipeline['workspace_name'],
                    table_name=f"table_{fake.word()}",
                    pipeline_name=pipeline['name']
                ).set(latency)

    def generate_sql_metrics(self):
        """Generate SQL warehouse metrics"""
        with self.tracer.start_as_current_span("generate_sql_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            for warehouse in self.warehouses:
                # Warehouse status
                is_up = warehouse['status'] == 'RUNNING'
                self.sql_warehouse_up.labels(
                    workspace=warehouse['workspace_name'],
                    warehouse_id=warehouse['id'],
                    warehouse_name=warehouse['name']
                ).set(1 if is_up else 0)
                
                if is_up:
                    # Query failures
                    if random.random() < self.config.failure_rate * 0.3:
                        failures = random.randint(1, 3)
                        self.sql_query_failures.labels(
                            workspace=warehouse['workspace_name'],
                            warehouse_id=warehouse['id'],
                            warehouse_name=warehouse['name']
                        )._value._value += failures
                    
                    # Query duration
                    query_time = random.gauss(5, 3)
                    query_time = max(0.1, min(60, query_time))  # 0.1 to 60 seconds
                    self.sql_query_duration.labels(
                        workspace=warehouse['workspace_name'],
                        warehouse_id=warehouse['id'],
                        warehouse_name=warehouse['name']
                    ).observe(query_time)

    def generate_dbfs_metrics(self):
        """Generate DBFS metrics"""
        with self.tracer.start_as_current_span("generate_dbfs_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            # Random DBFS errors
            if random.random() < self.config.failure_rate * 0.2:
                operations = ['read', 'write', 'delete', 'list', 'mkdir']
                operation = random.choice(operations)
                self.dbfs_errors.labels(
                    workspace=random.choice(self.workspaces)['name'],
                    operation=operation,
                    path=f"/{fake.word()}/{fake.word()}"
                )._value._value += 1
            
            # DBFS usage
            for workspace in self.workspaces:
                usage = random.gauss(60, 20)
                usage = max(0, min(100, usage))
                self.dbfs_usage.labels(
                    workspace=workspace['name'],
                    mount_point=f"/mnt/{fake.word()}"
                ).set(usage)

    def generate_unity_catalog_metrics(self):
        """Generate Unity Catalog metrics"""
        with self.tracer.start_as_current_span("generate_unity_catalog_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            # Access denied events
            if random.random() < self.config.failure_rate * 0.1:
                workspace = random.choice(self.workspaces)
                self.unity_catalog_access_denied.labels(
                    workspace=workspace['name'],
                    catalog=f"catalog_{fake.word()}",
                    schema=f"schema_{fake.word()}",
                    user=fake.user_name()
                )._value._value += 1
            
            # Query duration
            for workspace in self.workspaces[:3]:  # Sample a few workspaces
                query_time = random.gauss(2, 1)
                query_time = max(0.1, min(10, query_time))  # 0.1 to 10 seconds
                self.unity_catalog_query_duration.labels(
                    workspace=workspace['name'],
                    catalog=f"catalog_{fake.word()}",
                    schema=f"schema_{fake.word()}"
                ).observe(query_time)

    def generate_spark_metrics(self):
        """Generate Spark application metrics"""
        with self.tracer.start_as_current_span("generate_spark_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            # Task failures
            if random.random() < self.config.failure_rate * 0.4:
                workspace = random.choice(self.workspaces)
                app_id = f"application_{fake.uuid4()[:8]}"
                stage_id = random.randint(1, 10)
                failures = random.randint(1, 10)
                self.spark_task_failed.labels(
                    workspace=workspace['name'],
                    application_id=app_id,
                    stage_id=str(stage_id)
                )._value._value += failures
            
            # Stage failures
            if random.random() < self.config.failure_rate * 0.2:
                workspace = random.choice(self.workspaces)
                app_id = f"application_{fake.uuid4()[:8]}"
                self.spark_stage_failed.labels(
                    workspace=workspace['name'],
                    application_id=app_id
                )._value._value += 1
            
            # GC time
            for workspace in self.workspaces[:5]:  # Sample a few workspaces
                app_id = f"application_{fake.uuid4()[:8]}"
                executor_id = f"executor_{fake.uuid4()[:8]}"
                gc_time = random.gauss(5, 3)
                gc_time = max(0, min(30, gc_time))  # 0 to 30 percent
                self.spark_gc_time.labels(
                    workspace=workspace['name'],
                    application_id=app_id,
                    executor_id=executor_id
                ).set(gc_time)

    def generate_slo_metrics(self):
        """Generate SLO-related metrics"""
        with self.tracer.start_as_current_span("generate_slo_metrics") as span:
            span.set_attribute("component", "telemetry_generator")
            
            slo_names = ['job_latency', 'pipeline_throughput', 'query_response_time']
            services = ['etl_service', 'ml_service', 'analytics_service']
            
            for slo_name in slo_names:
                for service in services:
                    workspace = random.choice(self.workspaces)
                    
                    # SLO burn rate
                    burn_rate = random.gauss(0.5, 0.3)
                    burn_rate = max(0, min(2, burn_rate))
                    self.slo_burn_rate.labels(
                        workspace=workspace['name'],
                        slo_name=slo_name,
                        service=service
                    ).set(burn_rate)
                    
                    # Error budget remaining
                    error_budget = random.gauss(85, 15)
                    error_budget = max(0, min(100, error_budget))
                    self.error_budget_remaining.labels(
                        workspace=workspace['name'],
                        slo_name=slo_name,
                        service=service
                    ).set(error_budget)

    def generate_logs(self):
        """Generate Databricks-style logs"""
        with self.tracer.start_as_current_span("generate_logs") as span:
            span.set_attribute("component", "telemetry_generator")
            
            log_entries = []
            
            # Cluster logs
            for cluster in random.sample(self.clusters, min(3, len(self.clusters))):
                log_entry = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': random.choice(['INFO', 'WARN', 'ERROR', 'DEBUG']),
                    'component': 'cluster',
                    'workspace': cluster['workspace_name'],
                    'cluster_id': cluster['id'],
                    'message': f"Cluster {cluster['name']} status: {cluster['status']}"
                }
                log_entries.append(log_entry)
            
            # Job logs
            for job in random.sample(self.jobs, min(3, len(self.jobs))):
                log_entry = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': random.choice(['INFO', 'WARN', 'ERROR']),
                    'component': 'job',
                    'workspace': job['workspace_name'],
                    'job_id': job['id'],
                    'run_id': job['last_run_id'],
                    'message': f"Job {job['name']} run {job['last_run_status']} with duration {random.randint(60, 3600)}s"
                }
                log_entries.append(log_entry)
            
            # Notebook logs
            for notebook in random.sample(self.notebooks, min(2, len(self.notebooks))):
                log_entry = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': random.choice(['INFO', 'WARN', 'ERROR']),
                    'component': 'notebook',
                    'workspace': notebook['workspace_name'],
                    'notebook_name': notebook['name'],
                    'message': f"Notebook {notebook['name']} executed successfully in {random.randint(10, 300)}s"
                }
                log_entries.append(log_entry)
            
            # Send logs to Loki
            try:
                headers = {'Content-Type': 'application/json'}
                for entry in log_entries:
                    payload = {
                        'streams': [{
                            'stream': {
                                'job': 'telemetry-generator',
                                'component': entry['component'],
                                'workspace': entry['workspace'],
                                'level': entry['level']
                            },
                            'values': [
                                [str(int(time.time() * 1000000000)), entry['message']]
                            ]
                        }]
                    }
                    response = requests.post(self.config.loki_endpoint, 
                                             json=payload, 
                                             headers=headers,
                                             timeout=5)
                    if response.status_code != 204:
                        logger.error("Failed to send log to Loki", 
                                   status_code=response.status_code,
                                   response=response.text)
            except Exception as e:
                logger.error("Error sending logs to Loki", error=str(e))

    def generate_traces(self):
        """Generate distributed traces"""
        with self.tracer.start_as_current_span("generate_traces") as span:
            span.set_attribute("component", "telemetry_generator")
            
            # Simulate a Databricks job execution trace
            with self.tracer.start_as_current_span("databricks_job_execution") as job_span:
                job_span.set_attribute("databricks.workspace", random.choice(self.workspaces)['name'])
                job_span.set_attribute("databricks.job_id", random.choice(self.jobs)['id'])
                job_span.set_attribute("databricks.job_name", random.choice(self.jobs)['name'])
                job_span.set_attribute("databricks.environment", random.choice(['prod', 'staging']))
                job_span.set_attribute("databricks.team", random.choice(['data-platform', 'ml-team']))
                
                # Cluster startup span
                with self.tracer.start_as_current_span("cluster_startup") as cluster_span:
                    cluster_span.set_attribute("databricks.cluster_id", random.choice(self.clusters)['id'])
                    cluster_span.set_attribute("databricks.instance_type", "i3.xlarge")
                    cluster_span.set_attribute("databricks.num_workers", "4")
                    time.sleep(random.uniform(0.1, 0.5))
                
                # Notebook execution span
                with self.tracer.start_as_current_span("notebook_execution") as notebook_span:
                    notebook_span.set_attribute("databricks.notebook_name", random.choice(self.notebooks)['name'])
                    notebook_span.set_attribute("databricks.language", "python")
                    
                    # Cell execution spans
                    for i in range(random.randint(3, 8)):
                        with self.tracer.start_as_current_span(f"cell_{i+1}_execution") as cell_span:
                            cell_span.set_attribute("databricks.cell_id", str(i+1))
                            cell_span.set_attribute("databricks.cell_type", random.choice(['code', 'markdown']))
                            time.sleep(random.uniform(0.05, 0.2))
                            
                            # Random cell failure
                            if random.random() < self.config.failure_rate * 0.2:
                                cell_span.set_status(trace.Status(trace.StatusCode.ERROR, "Cell execution failed"))
                                cell_span.record_exception(Exception("Simulated cell failure"))
                
                # Spark task spans
                with self.tracer.start_as_current_span("spark_task_execution") as spark_span:
                    spark_span.set_attribute("spark.application_id", f"application_{fake.uuid4()[:8]}")
                    spark_span.set_attribute("spark.stage_id", str(random.randint(1, 10)))
                    spark_span.set_attribute("spark.task_id", str(random.randint(1, 100)))
                    
                    # Executor spans
                    for i in range(random.randint(2, 5)):
                        with self.tracer.start_as_current_span(f"executor_{i+1}_task") as executor_span:
                            executor_span.set_attribute("spark.executor_id", f"executor_{i+1}")
                            executor_span.set_attribute("spark.task_duration", str(random.uniform(1, 10)))
                            time.sleep(random.uniform(0.01, 0.1))

    def push_metrics_to_prometheus(self):
        """Push metrics to Prometheus Pushgateway"""
        try:
            push_to_gateway(self.config.prometheus_gateway, 
                           job='databricks_telemetry', 
                           registry=self.registry)
            logger.debug("Metrics pushed to Prometheus")
        except Exception as e:
            logger.error("Failed to push metrics to Prometheus", error=str(e))

    def send_kafka_events(self):
        """Send events to Kafka"""
        if not self.kafka_producer:
            return
        
        try:
            # Generate various Databricks events
            events = []
            
            # Job events
            for job in random.sample(self.jobs, min(2, len(self.jobs))):
                event = {
                    'event_type': 'job_run',
                    'timestamp': datetime.utcnow().isoformat(),
                    'workspace': job['workspace_name'],
                    'job_id': job['id'],
                    'job_name': job['name'],
                    'run_id': fake.uuid4()[:8],
                    'status': random.choice(['SUCCEEDED', 'FAILED', 'RUNNING']),
                    'duration_seconds': random.randint(60, 3600)
                }
                events.append(event)
            
            # Cluster events
            for cluster in random.sample(self.clusters, min(2, len(self.clusters))):
                event = {
                    'event_type': 'cluster_status_change',
                    'timestamp': datetime.utcnow().isoformat(),
                    'workspace': cluster['workspace_name'],
                    'cluster_id': cluster['id'],
                    'cluster_name': cluster['name'],
                    'old_status': 'Terminated',
                    'new_status': 'Running',
                    'driver_node_type': cluster['instance_type'],
                    'num_workers': cluster['num_workers']
                }
                events.append(event)
            
            # Send events to Kafka
            for event in events:
                self.kafka_producer.send('databricks-events', event)
            
            self.kafka_producer.flush()
            logger.debug("Events sent to Kafka")
        except Exception as e:
            logger.error("Failed to send events to Kafka", error=str(e))

    def run(self):
        """Main execution loop"""
        logger.info("Starting Databricks telemetry generation")
        
        while True:
            try:
                # Generate all metrics
                self.generate_cluster_metrics()
                self.generate_job_metrics()
                self.generate_pipeline_metrics()
                self.generate_sql_metrics()
                self.generate_dbfs_metrics()
                self.generate_unity_catalog_metrics()
                self.generate_spark_metrics()
                self.generate_slo_metrics()
                
                # Push metrics to Prometheus
                self.push_metrics_to_prometheus()
                
                # Generate logs
                self.generate_logs()
                
                # Generate traces
                self.generate_traces()
                
                # Send Kafka events
                self.send_kafka_events()
                
                logger.info("Telemetry generation cycle completed")
                
                # Wait for next cycle
                time.sleep(self.config.generation_interval)
                
            except KeyboardInterrupt:
                logger.info("Stopping telemetry generation")
                break
            except Exception as e:
                logger.error("Error in telemetry generation cycle", error=str(e))
                time.sleep(self.config.generation_interval)

def main():
    """Main entry point"""
    config = Config()
    generator = DatabricksTelemetryGenerator(config)
    
    try:
        generator.run()
    except KeyboardInterrupt:
        logger.info("Databricks Telemetry Generator stopped")
    except Exception as e:
        logger.error("Fatal error in telemetry generator", error=str(e))

if __name__ == "__main__":
    main()
