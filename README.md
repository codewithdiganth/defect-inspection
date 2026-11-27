# AI Visual Quality Inspection

A Django and Django REST Framework application for product-image inspections. Celery workers run the supplied frozen classifier, with Redis as the task broker. SQLite is the local default; PostgreSQL can be selected with environment variables.

## Requirements

- Python 3.11 or newer
- Redis 5 or newer
- The project pack in the repository root:
  - `Model/inference.py` and `Model/classifier.npz`
  - `Samples/images/` and `Samples/labels.csv`
  - `Validation/not_an_image.jpg`, `Validation/corrupt_image.png`, and `Validation/too_small.png`
  - `product_details.csv`

The evaluation labels are used only to compute metrics after predictions; they are never read by the inference function. Do not edit the supplied model files.

## Linux and macOS setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
set -a
source .env
set +a
python manage.py migrate
python manage.py seed_demo
```

For the default SQLite setup, no database server is needed. To use PostgreSQL, create a database and user, then edit `.env` to set:

```dotenv
DB_ENGINE=django.db.backends.postgresql
DB_NAME=visual_inspection
DB_USER=postgres
DB_PASSWORD=your-local-password
DB_HOST=localhost
DB_PORT=5432
```

Install/start PostgreSQL separately, then rerun the migrations. Do not commit `.env`.

## Windows setup (PowerShell)

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
$env:DJANGO_SECRET_KEY = "replace-this-with-a-long-random-secret"
$env:DJANGO_DEBUG = "true"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:DB_ENGINE = "django.db.backends.sqlite3"
$env:DB_NAME = "db.sqlite3"
$env:CELERY_BROKER_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
$env:CELERY_TASK_ALWAYS_EAGER = "false"
python manage.py migrate
python manage.py seed_demo
```

For PostgreSQL, set `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in the PowerShell session before running migrations.

## Start the application

Start Redis in its own terminal. If Redis is installed locally:

```bash
redis-server
```

Or run it with Docker:

```bash
docker run --name visual-inspection-redis --rm -p 6379:6379 redis
```

Start a Celery worker in another terminal. Use `--pool=solo` for Windows:

```bash
celery -A config worker -l info --pool=solo
```

On Linux or macOS, the default worker pool is also supported:

```bash
celery -A config worker --loglevel=info
```

Start Django in another terminal:

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Demo accounts

Run `python manage.py seed_demo` to create or update these users and the product in `product_details.csv`:

| Role | Username | Password |
|---|---|---|
| Administrator | `admin1` | `Demo@12345` |
| Engineer | `eng1` | `Demo@12345` |
| Supervisor | `sup1` | `Demo@12345` |

Change these demo credentials before using the app beyond a local demonstration.

## Demo script

1. Sign in as `admin1`, open **Products**, and verify/register `P-PLATE01`.
2. Sign in as `eng1`, select the product, choose one valid sample, and upload it. Follow the item on its batch status page.
3. Upload a mixed batch containing one valid image and `Validation/not_an_image.jpg`. The valid item should process; the invalid item should fail with a validation message and no prediction.
4. Open **History**, filter by prediction or review status, and inspect the original prediction.
5. Sign in as `sup1`, open the inspection, correct or confirm its reviewed class, and reload the record. The original model output and separate review should both remain visible.
6. Attempt the review endpoint as `eng1`; it should return HTTP 403 and create or change no review.
7. Run `python manage.py evaluate_samples`, then sign in as `sup1` or `admin1` and open **Metrics** to inspect its confusion matrix and defect recall. A small synthetic dataset, fixed image framing, uncalibrated confidence scores, and only 60 samples limit any claim of real-world reliability.

## Evaluation and tests

Run the classifier against all labeled sample images, print metrics and validation fixture outcomes, and write `evaluation_report.md`:

```bash
python manage.py evaluate_samples
```

The latest generated report is available at `/metrics/` to Supervisors and Administrators.

Optional arguments for alternate fixture locations:

```bash
python manage.py evaluate_samples --samples-dir Samples --validation-dir Validation --report-path evaluation_report.md
```

Run all Django tests and configuration checks:

```bash
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

The test suite does not require Redis or the model pack; Celery and prediction are mocked where appropriate. Set `CELERY_TASK_ALWAYS_EAGER=true` to run actual tasks synchronously when a model is available.

## API overview

- `POST /api/inspections/` — multipart upload (`product_id`, 1–10 `files`)
- `GET /api/inspections/` — paginated, role-scoped inspection history and filters
- `GET /api/inspections/<id>/` — scoped inspection detail, original output, and separate review
- `POST /api/inspections/<id>/review/` — completed inspection review, Supervisor only
- `GET /api/batches/<id>/` — scoped batch status
- `GET /api/products/`, `POST /api/products/`, `GET/PUT/DELETE /api/products/<id>/` — authenticated product reads; Administrator writes only
