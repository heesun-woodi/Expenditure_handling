# 지출품의서 자동화 AI Agent

Slack 기반 영수증 처리 자동화 시스템

---

## 프로젝트 개요

개인 카드 영수증을 Slack에 업로드하면 AI가 자동으로 분석하여 Google Sheets 지출품의서를 작성하는 자동화 에이전트입니다.

### 주요 기능

- 영수증 이미지 자동 분석 (Claude Vision AI)
- Google Sheets 자동 작성 및 계산
- Slack 기반 워크플로우 관리
- 휴먼 검토 프로세스 지원

---

## 문서 구조

```
📂 Expenditure_handling/
├── 📄 README.md                          # 프로젝트 개요 (이 파일)
├── 📂 docs/                              # 상세 문서
│   ├── 01_PRD.md                         # 제품 요구사항 정의서
│   ├── 02_DATA_SPEC.md                   # 데이터 매핑 및 로직 명세서
│   ├── 03_AI_PROMPT_GUIDE.md             # AI 프롬프트 가이드
│   └── 04_IMPLEMENTATION_GUIDE.md        # 구현 가이드
└── 📂 영수증샘플.HEIC                     # 테스트용 영수증 샘플
```

---

## 빠른 시작

### 1. 문서 읽기 순서

개발을 시작하기 전에 다음 순서로 문서를 읽어주세요:

1. **[01_PRD.md](docs/01_PRD.md)** - 프로젝트 목표와 기능 이해
2. **[02_DATA_SPEC.md](docs/02_DATA_SPEC.md)** - 데이터 구조와 처리 로직 파악
3. **[03_AI_PROMPT_GUIDE.md](docs/03_AI_PROMPT_GUIDE.md)** - AI 분석 방법 학습
4. **[04_IMPLEMENTATION_GUIDE.md](docs/04_IMPLEMENTATION_GUIDE.md)** - 실제 구현 시작

### 2. Claude Code로 구현하기

`docs/04_IMPLEMENTATION_GUIDE.md`의 **섹션 1: Claude Code 프롬프트**를 복사하여 Claude Code에 붙여넣으면 자동으로 코드가 생성됩니다.

---

## 문서 설명

### 📄 01_PRD.md - 제품 요구사항 정의서
- 프로젝트 목표 및 핵심 기능
- 사용자 워크플로우 (Step 1~5)
- 성공 지표 및 향후 개선 계획

### 📄 02_DATA_SPEC.md - 데이터 매핑 및 로직 명세서
- Google Sheets 입력 규칙
- 금액 계산 로직 (공급가액/세액 분리)
- Slack 메시지 템플릿
- 데이터 유효성 검사 규칙

### 📄 03_AI_PROMPT_GUIDE.md - AI 프롬프트 가이드
- Claude Vision API 사용법
- 영수증 분석용 System Prompt
- API 호출 예시 코드 (Python)
- 정확도 향상 팁

### 📄 04_IMPLEMENTATION_GUIDE.md - 구현 가이드
- Claude Code 실행 프롬프트
- 환경 설정 방법 (Slack, Google Cloud, Claude API)
- 배포 가이드 (Docker, systemd)
- 트러블슈팅 및 FAQ

---

## 기술 스택

- **Language:** Python 3.9+
- **Slack:** Slack Bolt SDK (Socket Mode)
- **AI:** Claude 3.5 Sonnet (Vision)
- **Google Cloud:** Sheets API, Drive API
- **Database:** SQLite (선택사항)

---

## 개발 워크플로우

```
1. 문서 읽기 (docs/)
   ↓
2. 환경 설정 (Slack, Google, Claude)
   ↓
3. Claude Code로 코드 생성
   ↓
4. 로컬 테스트
   ↓
5. 배포 및 모니터링
```

---

## 프로젝트 상태

- [x] 문서 작성 완료
- [ ] 코드 구현 (Claude Code 사용)
- [ ] 테스트 완료
- [ ] 운영 배포

---

## 기여 방법

1. 문서 개선 제안: Pull Request 생성
2. 버그 리포트: Issues 등록
3. 기능 요청: Issues에 Feature Request 태그 사용

---

## 라이선스

MIT License

---

## 연락처

- **프로젝트 관리자:** 우디
- **기술 문의:** Slack #pj-foodcare 채널

---

**최종 업데이트:** 2026-02-07
