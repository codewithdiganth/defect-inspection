# All Commands - Copy Paste Ready

## Setup
```bash
python3 -m venv ~/hackathon/venv
source ~/hackathon/venv/bin/activate
cd ~/hackathon/round1
pip install -r requirements.txt
```

## Database
```bash
rm db.sqlite3
rm -rf manual_assistant/migrations
mkdir -p manual_assistant/migrations
touch manual_assistant/migrations/__init__.py
python manage.py makemigrations manual_assistant
python manage.py migrate
```

## Create Users
```bash
python manage.py shell
```
Then paste:
```python
from manual_assistant.models import User
User.objects.create_user('admin','admin@test.com','admin123', role='Admin')
User.objects.create_user('engineer','eng@test.com','eng123', role='Engineer')
User.objects.create_user('supervisor','sup@test.com','sup123', role='Supervisor')
exit()
```

## Run Server (Local)
```bash
pkill -f runserver; lsof -ti:8001 | xargs kill -9; sleep 1
cd ~/hackathon/round1
source ~/hackathon/venv/bin/activate
python manage.py runserver 8001
# Open http://127.0.0.1:8001/
```

## Run Server (Local Network - Same WiFi for Mobile)
```bash
ipconfig getifaddr en0
python manage.py runserver 0.0.0.0:8001
# Open on phone: http://192.168.1.5:8001 (replace with your IP)
```

## Run Server (Public via ngrok)
```bash
# Terminal 1
cd ~/hackathon/round1
source ~/hackathon/venv/bin/activate
python manage.py runserver 8001

# Terminal 2
ngrok http 8001
# Gives https://xxxx.ngrok-free.dev
# Add to core/settings.py: CSRF_TRUSTED_ORIGINS = ['https://*.ngrok-free.dev']
```

## Fix Logout (if 404)
```bash
cat > /tmp/fix_logout.py << 'PY'
import pathlib
urls_path = pathlib.Path.home() / "hackathon" / "round1" / "manual_assistant" / "urls.py"
urls_path.write_text('''from django.urls import path
from . import views
urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('admin-dashboard/', views.admin_dashboard),
    path('engineer/', views.engineer_view),
    path('supervisor/', views.supervisor_view),
    path('api/machines/', views.api_add_machine),
    path('api/manuals/upload/', views.api_upload_manual),
    path('api/ask/', views.api_ask),
    path('api/history/', views.api_history),
]
''')
views_path = pathlib.Path.home() / "hackathon" / "round1" / "manual_assistant" / "views.py"
text = views_path.read_text()
if "def logout_view" not in text:
    text = text.replace("    return render(request, 'login.html')\n\n@login_required", "    return render(request, 'login.html')\n\ndef logout_view(request):\n    logout(request)\n    return redirect('/')\n\n@login_required")
    views_path.write_text(text)
print("Fixed")
PY
python3 /tmp/fix_logout.py
```

## Install Beautiful Templates (One Command)
```bash
cat > /tmp/install.py << 'PY'
import pathlib
base = pathlib.Path.home() / "hackathon" / "round1" / "manual_assistant" / "templates"
base.mkdir(parents=True, exist_ok=True)
# Templates are embedded - see full version in README
# For quick install, copy from Manual_Assistant_Complete folder
PY
```

## Test Credentials
- Admin: admin / admin123 → /admin-dashboard/
- Engineer: engineer / eng123 → /engineer/ → Ask "What does E17 mean?"
- Supervisor: supervisor / sup123 → /supervisor/
