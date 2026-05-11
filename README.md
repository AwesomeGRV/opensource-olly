# Databricks Observability Stack

A complete open-source observability stack for simulating Databricks monitoring and pipeline observability. This project provides a realistic environment for SRE learning, incident response practice, and monitoring demonstrations.

## Features

### Core Components
- **Grafana** - Visualization and dashboards
- **Prometheus** - Metrics collection and storage
- **Loki** - Log aggregation
- **Tempo** - Distributed tracing
- **OpenTelemetry Collector** - Telemetry processing
- **Alertmanager** - Alert routing and notification
- **Node Exporter** - System metrics
- **cAdvisor** - Container metrics

### Additional Services
- **Kafka** - Message queue for event streaming
- **Redis** - Cache and session store
- **PostgreSQL** - Metadata and long-term storage
- **MinIO** - S3-compatible storage
- **Pyroscope** - Continuous profiling

### Simulated Databricks Telemetry
- **Cluster metrics** - CPU, memory, executor failures, costs
- **Job monitoring** - Failures, duration, queue time
- **Pipeline health** - Streaming lag, Delta latency
- **SQL warehouses** - Query performance, failures
- **Spark performance** - Task/stage failures, GC time
- **DBFS operations** - Errors, usage metrics
- **Unity Catalog** - Access control, query performance
- **SLO/SLA monitoring** - Error budgets, burn rates

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- At least 8GB RAM
- 20GB+ free disk space

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd databricks-observability-stack
   ```

2. **Start all services**
   ```bash
   docker-compose up -d
   ```

3. **Wait for services to be ready** (2-3 minutes)
   ```bash
   docker-compose ps
   ```

4. **Access the dashboards**
   - Grafana: http://localhost:3000 (admin/admin123)
   - Prometheus: http://localhost:9090
   - Alertmanager: http://localhost:9093
   - Loki: http://localhost:3100
   - Tempo: http://localhost:3200

5. **Verify telemetry generation**
   ```bash
   docker-compose logs -f telemetry-generator
   ```

## Service URLs and Credentials

| Service | URL | Credentials | Description |
|---------|-----|-------------|-------------|
| Grafana | http://localhost:3000 | admin/admin123 | Main dashboard interface |
| Prometheus | http://localhost:9090 | - | Metrics query interface |
| Alertmanager | http://localhost:9093 | - | Alert management |
| Loki | http://localhost:3100 | - | Log query interface |
| Tempo | http://localhost:3200 | - | Trace query interface |
| MinIO | http://localhost:9001 | minioadmin/minioadmin123 | Object storage |
| Kafka UI | http://localhost:8080 | - | Kafka management |
| Redis CLI | localhost:6379 | - | Redis interface |
| PostgreSQL | localhost:5432 | postgres/postgres123 | Database |

## Dashboards

### Available Dashboards

1. **Databricks Platform Overview**
   - Active clusters by workspace
   - Resource utilization trends
   - Cost overview
   - Recent error logs

2. **Pipeline Health**
   - Pipeline status overview
   - Streaming lag metrics
   - Delta table latency
   - Pipeline error logs

3. **Spark Performance**
   - Task/stage failure rates
   - GC time percentage
   - Spark traces
   - Performance logs

4. **Job Failures**
   - Current failed jobs
   - Failure rate trends
   - Queue time analysis
   - Job error logs

5. **Cost Monitoring**
   - Cost per hour/day/month
   - Cost by instance type
   - Idle time analysis
   - Cost optimization opportunities

6. **SLO/SLA Dashboard**
   - Error budget remaining
   - SLO burn rates
   - Service success rates
   - Performance SLAs

### Dashboard Features

- **Real-time updates** - 5-second refresh interval
- **Interactive filtering** - Workspace, service, and component filters
- **Drill-down capabilities** - Click through to detailed views
- **Alert integration** - Visual indicators for alert conditions
- **Export options** - PDF, PNG, and data export

## Configuration

### Environment Variables

Key environment variables in `docker-compose.yml`:

```yaml
environment:
  - PROMETHEUS_GATEWAY=http://prometheus:9091
  - LOKI_ENDPOINT=http://loki:3100/loki/api/v1/push
  - TEMPO_ENDPOINT=http://tempo:4317
  - GENERATION_INTERVAL=5        # Telemetry generation interval (seconds)
  - FAILURE_RATE=0.1             # Simulated failure rate (10%)
```

### Customizing Metrics

Edit `telemetry-generator/telemetry_generator.py` to:
- Adjust failure rates
- Add new metric types
- Modify data patterns
- Change workspace configurations

### Alert Configuration

Edit `prometheus/alert_rules.yml` to:
- Adjust alert thresholds
- Add new alert rules
- Modify alert labels and annotations

Edit `alertmanager/alertmanager.yml` to:
- Configure notification channels (Slack, email, webhook)
- Set up routing rules
- Customize alert templates

## Telemetry Generator

The Python telemetry generator simulates realistic Databricks telemetry:

### Generated Metrics

```python
# Cluster metrics
databricks_cluster_up
databricks_cluster_cpu_usage_percent
databricks_cluster_memory_usage_percent
databricks_cluster_executor_failures_total
databricks_cluster_cost_per_hour
databricks_cluster_idle_time_seconds

# Job metrics
databricks_job_failed
databricks_job_duration_seconds
databricks_job_queue_time_seconds

# Pipeline metrics
databricks_pipeline_failed
databricks_streaming_lag_seconds
databricks_delta_table_latency_seconds

# SQL metrics
databricks_sql_warehouse_up
databricks_sql_query_failures_total
databricks_sql_query_duration_seconds
```

### Generated Logs

Structured JSON logs with:
- Timestamp and severity levels
- Component and workspace labels
- Cluster, job, and notebook identifiers
- Error messages and stack traces

### Generated Traces

OpenTelemetry traces for:
- Job execution workflows
- Cluster startup sequences
- Notebook cell executions
- Spark task processing

## Alerting

### Predefined Alerts

- **Critical**: Cluster down, job failures, pipeline failures
- **Warning**: High resource usage, streaming lag, query timeouts
- **Info**: Unused clusters, cost optimization opportunities

### Alert Channels

Configure in `alertmanager/alertmanager.yml`:

```yaml
# Slack integration
slack_configs:
  - api_url: 'YOUR_SLACK_WEBHOOK_URL'
    channel: '#databricks-alerts'
    send_resolved: true

# Email notifications
email_configs:
  - to: 'team@company.com'
    send_resolved: true
```

### Alert Testing

Test alerts manually:

```bash
# Trigger a test alert
curl -XPOST http://localhost:9093/api/v1/alerts \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    }
  }]'
```

## Troubleshooting

### Common Issues

1. **Services not starting**
   ```bash
   # Check logs
   docker-compose logs <service-name>
   
   # Check resource usage
   docker stats
   ```

2. **No metrics in Grafana**
   ```bash
   # Check Prometheus targets
   curl http://localhost:9090/api/v1/targets
   
   # Check telemetry generator
   docker-compose logs telemetry-generator
   ```

3. **No logs in Loki**
   ```bash
   # Check Promtail configuration
   docker-compose logs promtail
   
   # Verify Loki health
   curl http://localhost:3100/ready
   ```

4. **No traces in Tempo**
   ```bash
   # Check OpenTelemetry collector
   docker-compose logs otel-collector
   
   # Verify Tempo health
   curl http://localhost:3200/ready
   ```

### Performance Tuning

1. **Reduce resource usage**
   - Increase `GENERATION_INTERVAL`
   - Reduce number of simulated workspaces
   - Lower data retention periods

2. **Improve query performance**
   - Add recording rules in Prometheus
   - Optimize Grafana queries
   - Use appropriate time ranges

3. **Scale for production**
   - Deploy to Kubernetes
   - Use external databases
   - Implement sharding

## Testing

### Health Checks

```bash
# Check all services
docker-compose ps

# Individual service health
curl http://localhost:3000/api/health     # Grafana
curl http://localhost:9090/-/healthy       # Prometheus
curl http://localhost:3100/ready          # Loki
curl http://localhost:3200/ready          # Tempo
```

### Load Testing

Generate additional load:

```bash
# Scale telemetry generator
docker-compose up -d --scale telemetry-generator=3

# Increase failure rate
docker-compose exec telemetry-generator \
  python -c "import os; os.environ['FAILURE_RATE']='0.3'"
```

### Data Validation

```bash
# Query Prometheus metrics
curl -G 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=sum(databricks_cluster_up)'

# Search Loki logs
curl -G 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={job="telemetry-generator"}' \
  --data-urlencode 'start=2023-01-01T00:00:00Z' \
  --data-urlencode 'end=2023-01-01T01:00:00Z'
```

## Production Migration

### Kubernetes Deployment

1. **Convert to Kubernetes manifests**
   ```bash
   # Use Kompose
   kompose convert -f docker-compose.yml -o k8s/
   ```

2. **Deploy to cluster**
   ```bash
   kubectl apply -f k8s/
   ```

3. **Configure persistent storage**
   ```yaml
   # Example PVC
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: prometheus-data
   spec:
     accessModes: ["ReadWriteOnce"]
     resources:
       requests:
         storage: 100Gi
   ```

### Scaling Considerations

- **Prometheus**: Use federation for multi-region
- **Loki**: Deploy in distributed mode
- **Tempo**: Configure backend storage (S3, GCS)
- **Grafana**: Use HA mode with PostgreSQL

### Security Hardening

- Enable authentication and authorization
- Use TLS for all communications
- Implement network policies
- Regular security updates
- Audit logging

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Telemetry     │    │   OpenTelemetry  │    │   Storage       │
│   Generator     │───▶│   Collector      │───▶│   Backends      │
│                 │    │                  │    │                 │
│ • Metrics       │    │ • Processing     │    │ • Prometheus    │
│ • Logs          │    │ • Enrichment     │    │ • Loki          │
│ • Traces        │    │ • Routing        │    │ • Tempo         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Visualization │    │   Alerting       │    │   Analytics     │
│                 │    │                  │    │                 │
│ • Grafana       │    │ • Alertmanager   │    │ • Pyroscope     │
│ • Dashboards    │    │ • Notifications  │    │ • Profiling     │
│ • Exploration   │    │ • Routing        │    │ • Analysis      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Grafana Labs for excellent observability tools
- OpenTelemetry community for standards
- Databricks for platform inspiration
- Prometheus monitoring ecosystem

## Support

For questions and support:

1. Check the troubleshooting section
2. Review GitHub issues
3. Create a new issue with detailed information
4. Join our community discussions

---

**Happy Observability!**
