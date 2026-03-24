# Порядок развертывания

## Подготовительные шаги
```bash
# Сервисный аккаунт k8s-sa с container-registry.images.puller
# Собираем образ приложения и отправляем его в Yandex Container Registry
cd app
docker build -t cr.yandex/crpo6vu6s0qt49e9utqh/flask-app:v1.0.0 .
docker push cr.yandex/crpo6vu6s0qt49e9utqh/flask-app:v1.0.0
x
# Разворачиваем в Yandex Cloud Kubernetes cluster и подключаемся к нему
yc managed-kubernetes cluster get-credentials --id catmo893nr95hiq7pg0m --external
kubectl config current-context
```
## 1. Namespace
```bash
kubectl apply -f kubernetes/namespace.yaml
```
## 2. Secrets
```bash
# для сервисного аккаунта создаем JSON-ключ
yc iam key create \
  --service-account-name k8s-sa \
  --output k8s-key.json

# создаем секрет из JSON-ключа
kubectl create secret docker-registry docker-registry-secret \
  --namespace=flask-app \
  --docker-server=cr.yandex \
  --docker-username=json_key \
  --docker-password="$(cat k8s-key.json)" \
  --dry-run=client -o yaml > kubernetes/secrets/docker-registry-secret.yaml

# применяем секрет
kubectl apply -f kubernetes/secrets/docker-registry-secret.yaml

# basic-auth-secret.yaml
kubectl apply -f kubernetes/secrets/basic-auth-secret.yaml
```
## 3. PostgreSQL (StatefulSet + HA)
```bash
Необходимо создать ноду, далее шаги по списку
# postgres-statefulset.yaml - сам PostgreSQL (3 реплики)
kubectl apply -f kubernetes/deployments/postgres-statefulset.yaml

# postgres-service.yaml - доступ к БД внутри кластера
kubectl apply -f kubernetes/services/postgres-service.yaml

# postgres-ha-service.yaml - создание HA service для балансировки нагрузки
kubectl apply -f kubernetes/services/postgres-ha-service.yaml

# wait-for-db.sh - скрипт для проверки готовности БД
kubectl create configmap wait-for-db \
  --namespace=flask-app \
  --from-file=scripts/wait-for-db.sh \
  --dry-run=client -o yaml > scripts/wait-for-db-configmap.yaml

kubectl apply -f scripts/wait-for-db-configmap.yaml
```
## 4. Job для инициализации БД
```bash
kubectl apply -f kubernetes/jobs/init-db-job.yaml
```
## 5. Flask Deployment
```bash
# app-config.yaml
kubectl apply -f kubernetes/configs/app-config.yaml

# flask-app-deployment.yaml
kubectl apply -f kubernetes/deployments/flask-app-deployment.yaml

# flask-app-service.yaml
kubectl apply -f kubernetes/services/flask-app-service.yaml
```
## 6. Ingress
```bash
# Установить Ingress controller 
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml

# Применить Ingress
kubectl apply -f kubernetes/ingress/app-ingress.yaml

# Проверить Ingress
kubectl get ingress -n flask-app
```