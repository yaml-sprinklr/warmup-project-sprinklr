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

---

kubernetes_job_v1.db_migrations: Creating...
kubernetes_job_v1.db_migrations: Creation complete after 0s [id=order-service/order-service-migrations]
kubernetes_manifest.elasticsearch_cluster[0]: Modifying...
kubernetes_manifest.elasticsearch_cluster[0]: Modifications complete after 0s
kubernetes_config_map.filebeat_config[0]: Modifying... [id=order-service/filebeat-config]
kubernetes_config_map.filebeat_config[0]: Modifications complete after 0s [id=order-service/filebeat-config]
kubernetes_manifest.kibana_instance[0]: Modifying...
╷
│ Error: Provider produced inconsistent result after apply
│
│ When applying changes to kubernetes_manifest.kibana_instance[0], provider
│ "provider[\"registry.terraform.io/hashicorp/kubernetes\"]" produced an unexpected new value: .object: wrong final value
│ type: incorrect object attributes.
│
│ This is a bug in the provider, which should be reported in the provider's own issue tracker.
╵


---

# Destroy logging stack components
terraform destroy \
  -target=kubernetes_manifest.kibana_instance \
  -target=kubernetes_manifest.elasticsearch_cluster \
  -target=helm_release.eck_operator \
  -auto-approve

# Re-apply safely (Phase 1)
terraform apply \
  -target=kubernetes_namespace.elastic_system \
  -target=helm_release.eck_operator \
  -target=kubernetes_namespace.order_service \
  -auto-approve

# Phase 2 (Everything else)
terraform apply -auto-approve


---


Error: job: order-service/filebeat-setup is not in complete state
│
│   with kubernetes_job_v1.filebeat_setup[0],
│   on filebeat-setup.tf line 3, in resource "kubernetes_job_v1" "filebeat_setup":
│    3: resource "kubernetes_job_v1" "filebeat_setup" {
│
╵