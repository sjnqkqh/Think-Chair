# Thinking Chair — EC2 배포 및 CI/CD 구축 기록

> 작성일: 2026-07-25
> 대상 인스턴스: `ec2-43-201-65-205.ap-northeast-2.compute.amazonaws.com` (Amazon Linux 2023, t3.micro)

---

## 2단계: EC2 컨테이너 배포

### 2.1 Homebrew + Docker 설치

Amazon Linux 2023에 Homebrew를 설치하고 brew로 Docker를 구성했다.

```bash
# EC2 접속
ssh -i thinking-chair-pem.pem ec2-user@ec2-43-201-65-205.ap-northeast-2.compute.amazonaws.com

# Homebrew 전제조건
sudo yum install -y git gcc make

# Homebrew 설치
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv bash)"' >> ~/.bashrc
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv bash)"

# Docker CLI + Engine + Compose
brew install docker docker-compose docker-engine
```

### 2.2 Docker 데몬 설정

brew docker-engine을 systemd로 운영하기 위해 세 가지 추가 설정이 필요했다.

| 문제 | 원인 | 해결 |
| --- | --- | --- |
| `docker-proxy` not found | dockerd가 brew bin 경로를 모름 | `/etc/docker/daemon.json`에 `userland-proxy-path` 명시 |
| `containerd` not found in PATH | systemd 실행 시 PATH에 brew bin 없음 | `override.conf`로 Service PATH 추가 |
| `iptables` not found | Amazon Linux 2023 기본 미포함 | `sudo yum install -y iptables-nft` |

```bash
# docker-proxy 경로
sudo mkdir -p /etc/docker
echo '{"userland-proxy-path": "/home/linuxbrew/.linuxbrew/bin/docker-proxy"}' \
  | sudo tee /etc/docker/daemon.json

# systemd PATH override
sudo mkdir -p /etc/systemd/system/homebrew.docker-engine.service.d
printf '[Service]\nEnvironment=PATH=/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' \
  | sudo tee /etc/systemd/system/homebrew.docker-engine.service.d/override.conf
sudo systemctl daemon-reload

# iptables
sudo yum install -y iptables-nft

# docker-compose 플러그인 인식
mkdir -p ~/.docker
echo '{"cliPluginsExtraDirs": ["/home/linuxbrew/.linuxbrew/lib/docker/cli-plugins"]}' \
  > ~/.docker/config.json

# 엔진 기동
sudo --preserve-env=HOME brew services start docker-engine
```

### 2.3 이미지 이전 및 컨테이너 실행

로컬(Mac Apple Silicon)에서 빌드된 `think-chair` 이미지가 ARM64여서 EC2(AMD64)에서 실행되지 않았다. `linux/amd64`로 재빌드 후 SSH 파이프로 전송했다.

```bash
# 로컬: amd64 rebuild
cd PycharmProjects/RAG-Integrated-AI
docker buildx build --platform linux/amd64 -t think-chair:amd64 --load .

# SSH 파이프 전송
docker save think-chair:amd64 | gzip \
  | ssh ec2-user@... "gunzip | docker load"

# .env 파일 전송
scp .env ec2-user@...:~/.env.think-chair

# 컨테이너 실행
docker run -d --name think-chair --restart unless-stopped \
  -p 8000:8000 --env-file ~/.env.think-chair \
  -v think-chair-data:/data think-chair:latest
```

### 2.4 확인

| 항목 | 상태 |
| --- | --- |
| Docker Engine | 29.6.2 (brew) |
| Docker Compose | 5.3.1 (brew) |
| think-chair 컨테이너 | Running (8000/tcp) |
| HTTP 응답 | 307 (로그인 페이지 정상) |
| 사용 모델 | DeepSeek v4 Flash |

---

## 3단계: GitHub Actions CI/CD 구축

### 3.1 ECR 저장소

로컬에서 AWS CLI로 ECR 저장소를 생성하고 첫 번째 이미지를 푸시했다.

```bash
aws ecr create-repository --repository-name think-chair --region ap-northeast-2

docker tag think-chair:amd64 \
  $ECR_REGISTRY/think-chair:latest

docker push $ECR_REGISTRY/think-chair:latest
```

**레지스트리:** `210327328587.dkr.ecr.ap-northeast-2.amazonaws.com/think-chair`

### 3.2 IAM 구성

| 엔터티 | 유형 | 용도 |
| --- | --- | --- |
| Root | 계정 | MFA, 비상용 |
| `think-chair-operation` | IAM 사용자 | 콘솔 관리 + CI/CD 공용 액세스 키 |
| `DEV_DEPLOY` | GitHub Environment | 시크릿 그룹 관리 |

정책: `AmazonEC2ContainerRegistryFullAccess` (ECR push/pull 모두 허용)

### 3.3 GitHub Actions 워크플로우

`main` 브랜치 푸시 시 자동으로 이미지를 빌드하고 EC2에 배포한다.

```yaml
# .github/workflows/deploy.yml (요약)
on: push → main

steps:
  1. actions/checkout@v4
  2. configure-aws-credentials@v6     # AWS 인증
  3. amazon-ecr-login@v2              # ECR 로그인
  4. docker/setup-buildx-action@v3
  5. docker/build-push-action@v6      # linux/amd64 빌드 + ECR push
  6. appleboy/ssh-action@v1           # SSH 접속 → docker pull + 재시작
```

### 3.4 GitHub Secrets (DEV_DEPLOY Environment)

| Secret | 값 |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | think-chair-operation 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | (상동) |
| `EC2_HOST` | `43.201.65.205` |
| `EC2_SSH_KEY` | PEM 파일 내용 |
| `ENV_FILE` | `.env` 파일 내용 |

### 3.5 배포 흐름

```
GitHub main push
  → GitHub Actions (ubuntu-latest)
    → docker buildx —platform linux/amd64
    → ECR push (latest + commit SHA)
    → SSH to EC2
      → printf '%s\n' "$ENV_FILE" > ~/.env.think-chair
      → docker pull from ECR
      → docker rm + docker run (재시작)
      → docker image prune -f
```

### 3.6 트러블슈팅

| 문제 | 원인 | 해결 |
| --- | --- | --- |
| `exec format error` | ARM64 이미지를 AMD64에서 실행 | `buildx --platform linux/amd64` 로 재빌드 |
| PAT push rejected | `.github/workflows/` 경로는 workflow scope 필요 | PAT에 `workflow` 스코프 추가 |
| `iptables not found` | Docker bridge 네트워크 의존성 | `sudo yum install -y iptables-nft` |

---

## 최종 구성

```
사용자 (로컬 Mac)
  └─ PyCharm + Docker Desktop
  └─ git push → GitHub main

GitHub Actions
  └─ Build → ECR → SSH → EC2

EC2 (Amazon Linux 2023)
  ├─ Homebrew → Docker 29.6.2
  ├─ ECR pull → think-chair 컨테이너
  ├─ Port 8000 오픈
  └─ think-chair-data volume (SQLite + 파일 저장소)
```

**배포 URL:** `http://43.201.65.205:8000`* 지금은 내려갔습니다!
