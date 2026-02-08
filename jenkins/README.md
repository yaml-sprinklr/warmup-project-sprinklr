# Jenkins local setup (Rancher Desktop, no pulls during CI)

## Prereqs
- Rancher Desktop running with containerd
- `nerdctl` available

## Pre-pull images (one-time)
```bash
nerdctl --namespace k8s.io pull jenkins/jenkins:lts-jdk17
nerdctl --namespace k8s.io pull ghcr.io/astral-sh/uv:python3.14-bookworm-slim
```

## Run Jenkins controller locally
```bash
nerdctl --namespace k8s.io run -d --name jenkins \
  -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  jenkins/jenkins:lts-jdk17
```

Get the initial admin password:
```bash
nerdctl --namespace k8s.io exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

## Zero pulls during pipeline runs
- The Jenkinsfile uses `--pull=never` for both `build` and `run`.
- Ensure images are pre-pulled (`jenkins/jenkins:lts-jdk17`, `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`) and any base images you use.

## Stop Jenkins
```bash
nerdctl --namespace k8s.io stop jenkins && nerdctl --namespace k8s.io rm jenkins
```
