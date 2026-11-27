# Manual Assistant - AI-Powered RAG System | Hackathon Round 1

## Project Overview
Industrial machines (HP200, AC90) have 100+ page PDF manuals. Engineers waste hours searching for error codes like E17. This system uses RAG to give machine-specific answers with page number citations.

**Live URLs:**
- Local: http://127.0.0.1:8001/
- Local Network: http://192.168.x.x:8001 (via 0.0.0.0)
- Public (ngrok): https://proposal-vertebrae-frantic.ngrok-free.dev

**Login Credentials:**
- Admin: admin / admin123 → Can add machines + upload manuals
- Engineer: engineer / eng123 → Can ask questions with citations
- Supervisor: supervisor / sup123 → Can view Q&A history

---

## Why We Use Each Technology

### Backend

#### 1. Django 4.2 (Why?)
- **Why:** Full-featured Python web framework, built-in auth, ORM, admin, rapid development for hackathon
- **Alternative:** Flask (too minimal), FastAPI (good but no built-in auth UI)
- **Usage:** Handles login, role-based access, serves templates, REST APIs

#### 2. Django REST Framework (Why?)
- **Why:** Easy to create API endpoints like /api/machines/, /api/manuals/upload/, /api/ask/ with permission classes
- **Usage:** @api_view(['POST']) + @permission_classes([IsAuthenticated]) for role checks

#### 3. PyMuPDF (fitz) (Why?)
- **Why:** Fastest PDF text extraction in Python, gives text per page with page numbers, preserves layout
- **Alternative:** PyPDF2 (slow, no page numbers), pdfminer (complex)
- **Usage:** 
  ```python
  import fitz
  doc = fitz.open(pdf_path)
  for page_num, page in enumerate(doc):
      text = page.get_text()  # Keep page_number for citations
  ```

#### 4. ChromaDB (Why?)
- **Why:** Lightweight vector database, no need for separate server like Pinecone, persistent storage, supports where filters (critical for machine isolation)
- **Alternative:** FAISS (no metadata filter), Pinecone (paid, cloud)
- **Usage:**
  ```python
  collection.query(query_embeddings=[q_emb], where={"machine_id": "M-HP200"}, n_results=3)
  ```
  This where filter ensures M-HP200 ≠ M-AC90 isolation

#### 5. sentence-transformers (all-MiniLM-L6-v2) (Why?)
- **Why:** 384-dim embeddings, fast, good for semantic search, runs locally no API key needed, 80MB model
- **Alternative:** OpenAI embeddings (needs API key, paid), BERT large (slow, 1GB)
- **Usage:** Converts chunks and questions to vectors for similarity search

#### 6. SQLite (Why?)
- **Why:** Default Django DB, file-based, no setup, enough for hackathon, stores Machine, Manual, QuestionLog, User
- **Usage:** db.sqlite3 file

### Frontend

#### 7. Bootstrap 5.3 (Why?)
- **Why:** Ready-made responsive grid, cards, badges, no need to write CSS from scratch, looks professional for judges
- **Usage:** card-modern, badge, btn, container-fluid, row/col

#### 8. FontAwesome 6.4 (Why?)
- **Why:** 2000+ icons, one line <i class="fas fa-tools">, makes UI beautiful
- **Usage:** Shield, tools, chart-line, book-open, file-pdf, etc.

#### 9. Vanilla JS Fetch API (Why?)
- **Why:** No need for React/Vue for hackathon, simple fetch() for API calls, keeps project lightweight
- **Usage:** fetch('/api/ask/', {method:'POST', body: JSON.stringify({machine_id, question})})

---

## Complete Folder Structure
```
round1/
├── manage.py
├── requirements.txt
├── db.sqlite3 (created after migrate)
├── core/
│   ├── settings.py (CSRF_TRUSTED_ORIGINS for ngrok)
│   └── urls.py (includes manual_assistant.urls)
├── manual_assistant/
│   ├── models.py (Machine, Manual, QuestionLog, User)
│   ├── views.py (login, admin, engineer, supervisor, APIs)
│   ├── urls.py (login, logout, admin-dashboard, engineer, supervisor, apis)
│   ├── rag_service.py (extract_and_index, query_rag)
│   └── templates/
│       ├── login.html (beautiful role cards)
│       ├── admin.html (sidebar + stats + upload)
│       ├── engineer.html (machine selector + ask + citations)
│       └── supervisor.html (stats + history table)
└── media/
    └── manuals/ (uploaded PDFs)
```

---

## Complete Commands - Step by Step

### 1. Setup Virtual Environment (Why? Isolation)
```bash
# Why venv? Isolates project packages from system Python, avoids conflicts
python3 -m venv ~/hackathon/venv
source ~/hackathon/venv/bin/activate  # You must see (venv) in prompt
# If you don't activate, you'll get "zsh: command not found: python"
```

### 2. Install Dependencies (Why? Need libs)
```bash
cd ~/hackathon/round1
pip install -r requirements.txt
# This installs Django, PyMuPDF, ChromaDB, sentence-transformers, torch
```

### 3. Database Migration (Why? Create tables)
```bash
# Why migrate? Creates tables for User, Machine, Manual, QuestionLog
# First time, remove old DB if exists
rm db.sqlite3
rm -rf manual_assistant/migrations
mkdir -p manual_assistant/migrations
touch manual_assistant/migrations/__init__.py

python manage.py makemigrations manual_assistant
python manage.py migrate
# You should see "OK" for all migrations
# If you get "no such table: manual_assistant_user", you forgot to migrate
```

### 4. Create Users (Why? Role-based login)
```bash
python manage.py shell
# Inside shell, paste:
from manual_assistant.models import User
User.objects.create_superuser('admin','admin@test.com','admin123', role='Admin')
User.objects.create_user('engineer','eng@test.com','eng123', role='Engineer')
User.objects.create_user('supervisor','sup@test.com','sup123', role='Supervisor')
exit()
# Why 3 users? To test role isolation: Admin can upload, Engineer can ask, Supervisor can view history
```

### 5. Run Server - Local (Why? Test locally)
```bash
# Kill old servers first (Why? Port already in use error)
pkill -f runserver; lsof -ti:8001 | xargs kill -9; sleep 1

# Port 8000 often blocked on Mac, so use 8001
python manage.py runserver 8001
# Open Chrome: http://127.0.0.1:8001/
# Why 127.0.0.1? Only your laptop can access
```

### 6. Run Server - Local Network (Why? Test on mobile same WiFi)
```bash
# Find your IP
ipconfig getifaddr en0  # e.g. 192.168.1.5

python manage.py runserver 0.0.0.0:8001
# Now open on phone same WiFi: http://192.168.1.5:8001/
# Why 0.0.0.0? Binds to all interfaces, not just localhost
```

### 7. Run Server - Public via ngrok (Why? Judges can access anywhere)
```bash
# Install ngrok: brew install ngrok
# Signup at ngrok.com, get authtoken
ngrok config add-authtoken YOUR_TOKEN

# In Terminal 1: Keep Django running
python manage.py runserver 8001

# In Terminal 2: Start ngrok
ngrok http 8001
# You get public link: https://proposal-vertebrae-frantic.ngrok-free.dev
# Why ngrok? Gives public HTTPS URL for any device, no deployment needed

# IMPORTANT: Add to core/settings.py:
CSRF_TRUSTED_ORIGINS = ['https://*.ngrok-free.dev', 'https://*.ngrok.io', 'https://proposal-vertebrae-frantic.ngrok-free.dev']
# Why? Without this, Django gives CSRF verification failed Origin checking failed error on mobile
```

### 8. Add Machines & Upload Manuals (Why? Need data)
```bash
# Login as Admin: admin / admin123 at http://127.0.0.1:8001/
# Add Machine: M-HP200, name HP-200 and M-AC90, name AC90
# Why machines? To test isolation: E17 only in HP200, not AC90

# Upload Manuals (Admin only):
# Machine ID: M-HP200, Document ID: HP200_OPS, Revision: 1.0, File: HP200_Operations_Rev1_0.pdf
# Machine ID: M-HP200, Document ID: HP200_MNT, Revision: 1.0, File: HP200_Maintenance_Rev1_0.pdf
# Machine ID: M-AC90, Document ID: AC90_OPS, Revision: 1.0, File: AC90_Operations_Maintenance_Rev1_0.pdf
# Each returns {ok:true, chunks:12} - Why chunks? PyMuPDF extracts per page, splits into 500 token chunks for embedding
```

### 9. Test Engineer Ask (Why? Core feature)
```bash
# Logout: http://127.0.0.1:8001/logout/ (we added this URL because it was missing, gave 404)
# Login as Engineer: engineer / eng123
# Go to http://127.0.0.1:8001/engineer/
# Select M-HP200, Ask: "What does E17 mean?" -> Should get answer with Page number (e.g. Page 42)
# Select M-AC90, Ask same -> Should get "Available manuals do not contain enough information" -> status insufficient
# Why? This proves machine isolation via ChromaDB where filter
```

### 10. Test Supervisor History (Why? Audit)
```bash
# Logout, Login as Supervisor: supervisor / sup123
# Go to http://127.0.0.1:8001/supervisor/
# See table: Time, User, Machine, Question, Status (answered/insufficient), Answer preview
# Why? Supervisor can audit all Q&A
```

---

## Common Errors & Fixes (Why?)

1. **no such table: manual_assistant_user** → Forgot migrate, run python manage.py migrate
2. **zsh: command not found: python** → Forgot source ~/hackathon/venv/bin/activate, need (venv) in prompt
3. **Error: That port is already in use** → Multiple runserver tabs, run pkill -f runserver; lsof -ti:8001 | xargs kill -9
4. **CSRF verification failed Origin checking failed - https://...ngrok-free.dev does not match** → Add CSRF_TRUSTED_ORIGINS in settings.py
5. **Page not found at /logout/ (404)** → No logout URL, add path('logout/', views.logout_view) in manual_assistant/urls.py + def logout_view in views.py
6. **AssertionError .accepted_renderer not set on Response** → Used DRF Response in normal Django view @login_required without @api_view, fix to HttpResponse
7. **zsh: event not found: DOCTYPE** → Pasted HTML with ! into zsh, use cat << 'PY' with quotes around PY to disable history expansion
8. **ERR_NGROK_3200 or ERR_NGROK_4018** → Need both Django and ngrok running, need authtoken via ngrok config add-authtoken

---

## Demo for Judges

1. Login page beautiful design with 3 role cards
2. Admin dashboard: Add machine + Upload PDF with drag-drop, shows chunks indexed
3. Engineer: Select M-HP200, Ask E17 → Answer with page number + source passage + Open Page button
4. Engineer: Select M-AC90, Ask same → Insufficient → Proves isolation
5. Supervisor: History table with answered vs insufficient
6. Works on all devices: laptop (127.0.0.1), mobile same WiFi (0.0.0.0), public (ngrok)

---

## Why This Wins Round 1

- Complete requirements: Machine isolation ✓, Engineer cannot upload 403 ✓, Citations with page numbers ✓, RBAC ✓, RAG ✓
- Beautiful frontend + robust backend
- Real debugging: Fixed 8+ bugs (port, CSRF, logout, renderer, zsh, venv, ngrok, placeholder)
- Live demo ready
