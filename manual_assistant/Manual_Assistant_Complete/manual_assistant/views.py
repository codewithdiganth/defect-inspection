from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Machine, Manual, QuestionLog, User
from .rag_service import extract_and_index, query_rag
import os

def login_view(request):
    if request.method=='POST':
        u = authenticate(request, username=request.POST['username'], password=request.POST['password'])
        if u:
            login(request, u)
            if u.role=='Admin': return redirect('/admin-dashboard/')
            if u.role=='Engineer': return redirect('/engineer/')
            if u.role=='Supervisor': return redirect('/supervisor/')
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('/')

@login_required
def admin_dashboard(request):
    if request.user.role!='Admin': 
        return HttpResponse("Only Admin can access Admin Dashboard - You are logged in as: " + request.user.role, status=403)
    machines = Machine.objects.all()
    manuals = Manual.objects.all()
    return render(request, 'admin.html', {'machines':machines,'manuals':manuals})

@login_required
def engineer_view(request):
    if request.user.role!='Engineer': 
        return HttpResponse("Only Engineer can access Engineer page - You are logged in as: " + request.user.role + ". Please logout and login as Engineer.", status=403)
    machines = Machine.objects.all()
    return render(request, 'engineer.html', {'machines':machines})

@login_required
def supervisor_view(request):
    if request.user.role!='Supervisor': 
        return HttpResponse("Only Supervisor can access Supervisor page - You are logged in as: " + request.user.role, status=403)
    logs = QuestionLog.objects.all().order_by('-timestamp')
    return render(request, 'supervisor.html', {'logs':logs})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_machine(request):
    # Only Admin
    if request.user.role!='Admin':
        return Response({"error":"Only Admin can register machines"}, status=403)
    mid = request.data.get('machine_id')
    name = request.data.get('name','')
    Machine.objects.get_or_create(machine_id=mid, defaults={'name':name})
    return Response({"ok":True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_upload_manual(request):
    # 1st AUTOMATED CHECK: Engineers cannot upload
    if request.user.role=='Engineer':
        return Response({"error":"Engineers cannot upload manuals"}, status=403)
    if request.user.role!='Admin':
        return Response({"error":"Only Admin can upload"}, status=403)

    machine_id = request.data.get('machine_id')
    document_id = request.data.get('document_id')
    revision = request.data.get('revision')
    file = request.FILES.get('file')
    machine = Machine.objects.get(machine_id=machine_id)
    manual = Manual.objects.create(
        document_id=document_id, machine=machine, revision=revision,
        file=file, document_name=file.name, uploaded_by=request.user
    )
    count = extract_and_index(manual)
    return Response({"ok":True, "chunks":count})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_ask(request):
    if request.user.role!='Engineer':
        return Response({"error":"Only Engineer can ask"}, status=403)
    machine_id = request.data.get('machine_id')
    question = request.data.get('question')
    passages = query_rag(question, machine_id)

    if not passages:
        answer = "Available manuals do not contain enough information to answer this question."
        sources = []
        status = "insufficient"
    else:
        # Simple RAG answer (replace with LLM call if you have API key)
        # For hackathon, you can show passages as answer + use LLM
        combined = "\n".join([p['text'] for p in passages])
        # TODO: call OpenAI/Gemini here with combined as context
        # For now, mock answer from passages
        answer = f"Based on manuals: {combined[:800]}..."
        sources = [{"document_name":p['metadata']['document_name'],"document_id":p['metadata']['document_id'],"revision":p['metadata']['revision'],"page_number":p['metadata']['page_number'],"text":p['text'],"file_url":f"/media/manuals/{p['metadata']['document_name']}?page={p['metadata']['page_number']}"} for p in passages]
        status = "answered"
        # If LLM says insufficient, set status insufficient

    log = QuestionLog.objects.create(
        user=request.user, selected_machine_id=machine_id,
        question=question, answer=answer, sources=sources, status=status
    )
    return Response({"answer":answer, "sources":sources, "status":status, "log_id":log.id})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_history(request):
    if request.user.role=='Supervisor':
        logs = QuestionLog.objects.all().order_by('-timestamp').values()
    else:
        logs = QuestionLog.objects.filter(user=request.user).order_by('-timestamp').values()
    return Response(list(logs))
