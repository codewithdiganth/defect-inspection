# Why We Use Each Technology - Detailed

## Django - Why not Flask/FastAPI?
- Django has built-in User model, auth, admin, ORM - Flask needs extensions
- FastAPI is async but we need traditional templates for hackathon quick UI
- Django's @login_required decorator easy for role checks

## PyMuPDF vs PyPDF2 vs pdfminer
- PyMuPDF: 10x faster, page numbers, fitz.open() simple
- PyPDF2: Slow, loses formatting, no page metadata
- pdfminer: Complex API, slow

## ChromaDB vs FAISS vs Pinecone
- ChromaDB: Persistent, where filter, local, pip install chromadb
- FAISS: No where filter, need custom metadata handling, isolation hard
- Pinecone: Cloud, needs API key, paid after free tier

## sentence-transformers all-MiniLM-L6-v2 - Why?
- 384 dim, 80MB, fast on CPU, no GPU needed
- 768 dim models (bert-base) slow, 1GB
- OpenAI embeddings need API key, cost

## Bootstrap 5 - Why not Tailwind?
- Bootstrap has ready cards, no need to write CSS
- Tailwind needs build step, complex for hackathon
- FontAwesome icons work directly with Bootstrap

## SQLite - Why not PostgreSQL?
- SQLite file-based, no server setup, enough for 1000 Q&A logs
- PostgreSQL needs brew install, setup, overkill for hackathon

## ngrok - Why not Render?
- ngrok instant public link, no deploy, keeps local DB
- Render needs Git push, migrate, free tier sleeps
- For final submission, Render better for permanent link
