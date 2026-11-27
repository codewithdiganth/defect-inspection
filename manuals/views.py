from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Manual, Machine
from .forms import ManualForm
from inspections.permissions import ENGINEER, SUPERVISOR, has_role
from django.core.exceptions import PermissionDenied

def role_required(view):
    def wrapped(request, *args, **kwargs):
        if not has_role(request.user, ENGINEER) and not has_role(request.user, SUPERVISOR):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return login_required(wrapped)

@role_required
def manual_list(request):
    manuals = Manual.objects.select_related('machine', 'uploaded_by').order_by('-uploaded_at')
    return render(request, 'manuals/manual_list.html', {'manuals': manuals, 'role': request.user.role})

@role_required
def manual_upload(request):
    if request.method == 'POST':
        form = ManualForm(request.POST, request.FILES)
        if form.is_valid():
            manual = form.save(commit=False)
            manual.uploaded_by = request.user
            manual.save()
            return redirect('manual-list')
    else:
        form = ManualForm()
    return render(request, 'manuals/manual_upload.html', {'form': form})

@role_required
def manual_detail(request, pk):
    manual = get_object_or_404(Manual, pk=pk)
    return render(request, 'manuals/manual_detail.html', {'manual': manual})
