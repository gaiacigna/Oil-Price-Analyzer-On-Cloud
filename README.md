# Oil Price Analyzer On Cloud

Oil Price Analyzer è una pipeline containerizzata progettata per prevedere i prezzi del petrolio utilizzando tecnologie moderne e distribuite. Il progetto è completamente deployabile su Google Kubernetes Engine (GKE).

## Tecnologie Utilizzate
- **Docker**: Contenitori per ogni servizio.
- **Kubernetes (GKE)**: Orchestrazione dei container.
- **Spark**: Elaborazione dati e generazione delle previsioni.
- **Kafka**: Gestione dei flussi di dati.
- **Elasticsearch & Kibana**: Archiviazione e visualizzazione dei risultati.
- **Logstash**: Ingestione dei dati.

## Funzionalità
1. Ingestione dei dati tramite Logstash.
2. Elaborazione dati e previsioni con Spark.
3. Visualizzazione dei risultati su Kibana.
