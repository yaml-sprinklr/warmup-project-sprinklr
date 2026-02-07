elastic-system	elastic-operator-webhook	https
elastic-system	order-service-es-es-default	https
elastic-system	order-service-es-es-http	https
elastic-system	order-service-es-es-internal-http	https
elastic-system	order-service-es-es-transport	tls-transport
elastic-system	order-service-kibana-kb-http	https
5601

kubernetes_job_v1.db_migrations: Creation complete after 0s [id=order-service/order-service-migrations]
kubernetes_manifest.elasticsearch_cluster[0]: Modifying...
╷
│ Error: There was a field manager conflict when trying to apply the manifest for "elastic-system/order-service-es"
│
│   with kubernetes_manifest.elasticsearch_cluster[0],
│   on logging.tf line 63, in resource "kubernetes_manifest" "elasticsearch_cluster":
│   63: resource "kubernetes_manifest" "elasticsearch_cluster" {
│
│ The API returned the following conflict: "Apply failed with 1 conflict: conflict with \"elastic-operator\" using
│ elasticsearch.k8s.elastic.co/v1: .spec.nodeSets"
│
│ You can override this conflict by setting "force_conflicts" to true in the "field_manager" block.
╵
