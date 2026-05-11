# Troubleshooting Guide

## Quick Diagnostics

### Health Check Commands

```bash
# Check all services status
docker-compose ps

# Check service logs
docker-compose logs -f [service-name]

# Check resource usage
docker stats

# Check disk space
df -h

# Check memory usage
free -h
```

### Service-Specific Health Checks

```bash
# Grafana
curl http://localhost:3000/api/health

# Prometheus
curl http://localhost:9090/-/healthy

# Loki
curl http://localhost:3100/ready

# Tempo
curl http://localhost:3200/ready

# Alertmanager
curl http://localhost:9093/-/healthy

# Redis
docker-compose exec redis redis-cli ping

# PostgreSQL
docker-compose exec postgres pg_isready -U postgres

# Kafka
docker-compose exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092
```

## Common Issues and Solutions

### 1. Services Not Starting

**Symptoms:**
- Services show as `Exit` or `Restarting` in `docker-compose ps`
- Logs show connection errors
- Port conflicts

**Solutions:**

```bash
# Check for port conflicts
netstat -tulpn | grep :3000
netstat -tulpn | grep :9090

# Kill conflicting processes
sudo kill -9 <pid>

# Clean up Docker resources
docker system prune -f
docker volume prune -f

# Restart services
docker-compose down
docker-compose up -d
```

**Common Port Conflicts:**
- 3000 (Grafana)
- 9090 (Prometheus)
- 3100 (Loki)
- 3200 (Tempo)
- 9093 (Alertmanager)
- 5432 (PostgreSQL)
- 6379 (Redis)
- 9092 (Kafka)

### 2. No Metrics in Grafana

**Symptoms:**
- Dashboards show "No data"
- Prometheus queries return empty results
- Grafana datasource connection errors

**Diagnosis:**

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Prometheus metrics
curl http://localhost:9090/api/v1/query?query=up

# Check telemetry generator
docker-compose logs telemetry-generator

# Check pushgateway
curl http://localhost:9091/metrics
```

**Solutions:**

1. **Restart telemetry generator:**
   ```bash
   docker-compose restart telemetry-generator
   ```

2. **Check Prometheus configuration:**
   ```bash
   docker-compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
   ```

3. **Verify Pushgateway connectivity:**
   ```bash
   docker-compose exec telemetry-generator curl http://pushgateway:9091
   ```

4. **Check network connectivity:**
   ```bash
   docker network ls
   docker network inspect databricks-observability-stack_observability
   ```

### 3. No Logs in Loki

**Symptoms:**
- Loki queries return empty results
- Grafana logs panel shows no data
- Promtail connection errors

**Diagnosis:**

```bash
# Check Promtail logs
docker-compose logs promtail

# Check Loki readiness
curl http://localhost:3100/ready

# Test log ingestion
curl -X POST http://localhost:3100/loki/api/v1/push \
  -H 'Content-Type: application/json' \
  -d '{
    "streams": [{
      "stream": {"job": "test"},
      "values": [["'$(date +%s)000000000'", "test log"]]
    }]
  }'

# Query logs
curl -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="test"}' \
  --data-urlencode 'start=2023-01-01T00:00:00Z' \
  --data-urlencode 'end=2023-12-31T23:59:59Z'
```

**Solutions:**

1. **Restart Promtail:**
   ```bash
   docker-compose restart promtail
   ```

2. **Check Promtail configuration:**
   ```bash
   docker-compose exec promtail promtail --config.file=/etc/promtail/config.yml --dry-run
   ```

3. **Verify Loki storage:**
   ```bash
   docker-compose exec loki ls -la /loki/chunks
   ```

4. **Check log file permissions:**
   ```bash
   docker-compose exec promtail ls -la /var/log/
   ```

### 4. No Traces in Tempo

**Symptoms:**
- Tempo UI shows no traces
- Grafana trace panel empty
- OpenTelemetry collector errors

**Diagnosis:**

```bash
# Check Tempo health
curl http://localhost:3200/ready

# Check OpenTelemetry collector
docker-compose logs otel-collector

# Test trace ingestion
curl -X POST http://localhost:4317/v1/traces \
  -H 'Content-Type: application/json' \
  -d '{"resourceSpans": []}'

# Check Tempo metrics
curl http://localhost:3200/metrics
```

**Solutions:**

1. **Restart OpenTelemetry collector:**
   ```bash
   docker-compose restart otel-collector
   ```

2. **Check collector configuration:**
   ```bash
   docker-compose exec otel-collector otelcol-validator --config=/etc/otel-collector-config.yaml
   ```

3. **Verify Tempo storage:**
   ```bash
   docker-compose exec tempo ls -la /tmp/tempo/blocks
   ```

4. **Check network connectivity:**
   ```bash
   docker-compose exec telemetry-generator curl http://tempo:4317
   ```

### 5. Alertmanager Not Sending Alerts

**Symptoms:**
- Alerts firing but no notifications
- Alertmanager shows silent alerts
- Webhook failures

**Diagnosis:**

```bash
# Check Alertmanager status
curl http://localhost:9093/api/v1/status

# Check active alerts
curl http://localhost:9093/api/v1/alerts

# Test alert webhook
curl -X POST http://localhost:9093/api/v1/alerts \
  -H 'Content-Type: application/json' \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    }
  }]'

# Check Alertmanager logs
docker-compose logs alertmanager
```

**Solutions:**

1. **Verify Alertmanager configuration:**
   ```bash
   docker-compose exec alertmanager amtool config routes test
   ```

2. **Check webhook connectivity:**
   ```bash
   curl -X POST http://your-webhook-url -d '{"test": "data"}'
   ```

3. **Update Slack webhook URL:**
   ```bash
   # Edit alertmanager/alertmanager.yml
   # Replace YOUR_SLACK_WEBHOOK_URL with actual URL
   docker-compose restart alertmanager
   ```

### 6. High Memory Usage

**Symptoms:**
- System becomes slow
- Docker containers OOM killed
- Services restarting frequently

**Diagnosis:**

```bash
# Check memory usage
docker stats --no-stream

# Check system memory
free -h

# Check OOM events
dmesg | grep -i oom

# Check container limits
docker inspect <container-name> | grep -i memory
```

**Solutions:**

1. **Increase system memory or add swap:**
   ```bash
   # Add swap file
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

2. **Optimize Prometheus memory usage:**
   ```yaml
   # In docker-compose.yml
   command:
     - '--storage.tsdb.retention.time=7d'  # Reduce retention
     - '--storage.tsdb.wal-compression'   # Enable compression
   ```

3. **Reduce telemetry generation rate:**
   ```yaml
   environment:
     - GENERATION_INTERVAL=10  # Increase from 5 to 10 seconds
     - FAILURE_RATE=0.05       # Reduce failure rate
   ```

### 7. Disk Space Issues

**Symptoms:**
- Services failing to start
- Database connection errors
- Log files not being written

**Diagnosis:**

```bash
# Check disk usage
df -h

# Check Docker volumes
docker system df

# Check large files
find /var/lib/docker -type f -size +1G -exec ls -lh {} \;

# Check log sizes
docker-compose logs --tail=0 | wc -c
```

**Solutions:**

1. **Clean up Docker resources:**
   ```bash
   docker system prune -a -f
   docker volume prune -f
   ```

2. **Reduce data retention:**
   ```yaml
   # In docker-compose.yml
   command:
     - '--storage.tsdb.retention.time=3d'  # Prometheus
   ```

3. **Configure log rotation:**
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

### 8. Kafka Connection Issues

**Symptoms:**
- Telemetry generator can't connect to Kafka
- Kafka producer errors
- Missing event data

**Diagnosis:**

```bash
# Check Kafka status
docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list

# Check Zookeeper
docker-compose exec zookeeper zkServer.sh status

# Test Kafka connectivity
docker-compose exec kafka kafka-producer-perf-test.sh --topic test --num-records 100
```

**Solutions:**

1. **Restart Kafka services:**
   ```bash
   docker-compose restart zookeeper kafka
   ```

2. **Check Kafka configuration:**
   ```bash
   docker-compose exec kafka kafka-configs --bootstrap-server localhost:9092 --entity-type topics --describe
   ```

3. **Verify network connectivity:**
   ```bash
   docker-compose exec telemetry-generator telnet kafka 9092
   ```

## Performance Tuning

### Prometheus Optimization

```yaml
# Add to prometheus command in docker-compose.yml
command:
  - '--storage.tsdb.retention.time=7d'
  - '--storage.tsdb.wal-compression'
  - '--query.max-samples=50000000'
  - '--query.timeout=2m'
```

### Loki Optimization

```yaml
# Add to loki-config.yaml
limits_config:
  ingestion_rate_mb: 32
  ingestion_burst_size_mb: 64
  max_query_length: 721h
```

### Grafana Optimization

```yaml
# Add to grafana environment variables
environment:
  - GF_SMTP_ENABLED=true
  - GF_LOG_LEVEL=warn
  - GF_METRICS_ENABLED=false
```

## Monitoring the Stack

### Self-Monitoring Dashboard

Create a dashboard to monitor the observability stack itself:

**Key Metrics:**
- Prometheus target status
- Loki ingestion rate
- Tempo trace ingestion
- Alertmanager health
- Container resource usage

**Alert Rules:**
- Prometheus storage usage > 80%
- Loki ingestion failures
- Tempo backend errors
- Container restarts

### Log Analysis

```bash
# Follow all service logs
docker-compose logs -f

# Filter specific service logs
docker-compose logs -f prometheus | grep ERROR

# Export logs to file
docker-compose logs > stack-logs-$(date +%Y%m%d).log
```

## Backup and Recovery

### Data Backup

```bash
# Backup Prometheus data
docker run --rm -v databricks-observability-stack_prometheus_data:/data -v $(pwd):/backup alpine tar czf /backup/prometheus-backup-$(date +%Y%m%d).tar.gz -C /data .

# Backup Loki data
docker run --rm -v databricks-observability-stack_loki_data:/data -v $(pwd):/backup alpine tar czf /backup/loki-backup-$(date +%Y%m%d).tar.gz -C /data .

# Backup Grafana data
docker run --rm -v databricks-observability-stack_grafana_data:/data -v $(pwd):/backup alpine tar czf /backup/grafana-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Data Recovery

```bash
# Restore Prometheus data
docker run --rm -v databricks-observability-stack_prometheus_data:/data -v $(pwd):/backup alpine tar xzf /backup/prometheus-backup-YYYYMMDD.tar.gz -C /data

# Restart services
docker-compose restart prometheus
```

## Getting Help

### Collect Debug Information

```bash
# Create debug bundle
mkdir debug-$(date +%Y%m%d)
cd debug-$(date +%Y%m%d)

# System information
uname -a > system-info.txt
docker version > docker-version.txt
docker-compose version > compose-version.txt

# Service status
docker-compose ps > service-status.txt

# Configuration files
cp ../docker-compose.yml .
cp -r ../prometheus .
cp -r ../loki .
cp -r ../grafana .

# Logs
docker-compose logs > all-logs.txt

# Create archive
cd ..
tar czf debug-$(date +%Y%m%d).tar.gz debug-$(date +%Y%m%d)/
```

### Community Resources

- **Grafana Documentation**: https://grafana.com/docs/
- **Prometheus Documentation**: https://prometheus.io/docs/
- **Loki Documentation**: https://grafana.com/docs/loki/latest/
- **Tempo Documentation**: https://grafana.com/docs/tempo/latest/
- **OpenTelemetry Documentation**: https://opentelemetry.io/docs/

### Common Debug Commands

```bash
# Check container resource limits
docker inspect <container> | grep -A 10 -B 10 Memory

# Check network connectivity between containers
docker-compose exec container1 ping container2

# Check port bindings
docker port <container>

# Check volume mounts
docker inspect <container> | grep -A 10 Mounts

# Check environment variables
docker-compose exec <container> env | sort
```

## Prevention Tips

1. **Regular Maintenance**
   - Monitor disk space weekly
   - Clean up old logs monthly
   - Update containers regularly
   - Backup configurations

2. **Resource Planning**
   - Allocate sufficient memory (16GB+ recommended)
   - Monitor CPU usage during peak
   - Plan storage growth
   - Set up monitoring alerts

3. **Configuration Management**
   - Version control all configs
   - Document customizations
   - Test changes in staging
   - Use environment variables

4. **Monitoring Setup**
   - Set up alerts for critical services
   - Monitor resource usage
   - Track error rates
   - Set up log aggregation for stack logs
