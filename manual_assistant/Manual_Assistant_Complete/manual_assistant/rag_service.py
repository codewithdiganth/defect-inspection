
import fitz, uuid
from sentence_transformers import SentenceTransformer
import chromadb

# Load once
model = SentenceTransformer('all-MiniLM-L6-v2')
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection("manuals")

def extract_and_index(manual_obj):
    path = manual_obj.file.path
    doc = fitz.open(path)
    added = 0
    for page_num, page in enumerate(doc, start=1): # Rule: page 1 = PDF page 1
        text = page.get_text().strip()
        if len(text) < 50: continue
        # split into 500 char chunks
        chunks = [text[i:i+500] for i in range(0, len(text), 500)]
        for chunk in chunks:
            emb = model.encode(chunk).tolist()
            cid = str(uuid.uuid4())
            collection.add(
                ids=[cid],
                documents=[chunk],
                metadatas=[{
                    "machine_id": manual_obj.machine.machine_id,
                    "document_id": manual_obj.document_id,
                    "document_name": manual_obj.document_name,
                    "revision": manual_obj.revision,
                    "page_number": page_num,
                    "manual_pk": manual_obj.pk
                }],
                embeddings=[emb]
            )
            added+=1
    return added

def query_rag(question, selected_machine_id, top_k=3):
    q_emb = model.encode(question).tolist()
    # CRITICAL: machine isolation filter - 2nd automated check
    results = collection.query(
        query_embeddings=[q_emb],
        where={"machine_id": selected_machine_id},
        n_results=top_k
    )
    passages = []
    if results['documents']:
        for i in range(len(results['documents'][0])):
            passages.append({
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i]
            })
    return passages
