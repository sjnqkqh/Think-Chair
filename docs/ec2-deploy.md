# EC2 배포 가이드

## 1. 로컬: 프로젝트 압축

```bash
cd /Users/jungjin/PycharmProjects
tar -czf rag-integrated-ai.tar.gz \
  --exclude='RAG-Integrated-AI/__pycache__' \
  --exclude='RAG-Integrated-AI/**/__pycache__' \
  --exclude='RAG-Integrated-AI/chroma_db' \
  --exclude='RAG-Integrated-AI/*.db' \
  --exclude='RAG-Integrated-AI/*.db-shm' \
  --exclude='RAG-Integrated-AI/*.db-wal' \
  --exclude='RAG-Integrated-AI/.env' \
  --exclude='RAG-Integrated-AI/.venv' \
  --exclude='RAG-Integrated-AI/venv' \
  --exclude='RAG-Integrated-AI/.git' \
  --exclude='RAG-Integrated-AI/docs' \
  --exclude='RAG-Integrated-AI/pr-docs' \
  RAG-Integrated-AI
```

## 2. 로컬: EC2로 업로드

```bash
scp -i <your-key.pem> rag-integrated-ai.tar.gz ec2-user@<EC2_IP>:~/

# .env 파일은 별도 전송
scp -i <your-key.pem> RAG-Integrated-AI/.env ec2-user@<EC2_IP>:~/RAG-Integrated-AI/
```

## 3. EC2: 압축 해제 및 의존성 설치

```bash
tar -xzf ~/rag-integrated-ai.tar.gz -C ~/
cd ~/RAG-Integrated-AI

# uv 설치 (없는 경우)
curl -Lsf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# 의존성 설치
uv sync
```

## 4. EC2: 서버 실행

```bash
nohup uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &
echo $! > app.pid
```

### 실행 확인

```bash
sleep 3 && cat app.log
# 로그에 "Application startup complete." 가 보이면 정상
```

### 프로세스 확인

```bash
ps aux | grep uvicorn
cat app.pid && kill -0 $(cat app.pid) && echo "실행 중" || echo "종료됨"
```

## 5. EC2: 서버 종료

```bash
kill $(cat app.pid)

# pid 파일 없는 경우
pkill -f "uvicorn app.main:app"
```

## 6. 로컬: Health Check

```bash
# FastAPI 기본 문서 페이지
curl http://<EC2_IP>:8000/docs

# 루트 경로
curl http://<EC2_IP>:8000/
```

> EC2 보안 그룹 인바운드 규칙에 포트 8000 (TCP) 가 열려 있어야 합니다.

---

## 트러블슈팅

### ModuleNotFoundError 발생 시

`pyproject.toml`에 누락된 패키지를 추가하고 재설치:

```bash
uv add <패키지명>
```

**배포 과정에서 발견된 누락 패키지 (이미 추가 완료):**

| 패키지 | 원인 |
|---|---|
| `pydantic-settings` | `app/core/config.py`에서 import |
| `bcrypt` | 인증 관련 코드에서 import |
| `jinja2` | `fastapi.templating.Jinja2Templates` 사용 |

### import 전체 검증 방법 (로컬)

```bash
uv sync && python -c "import app.main"
# 에러 없이 종료되면 정상
```
