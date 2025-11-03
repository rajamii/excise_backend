from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from .models import Workflow, WorkflowStage, WorkflowTransition, StagePermission
from .serializers import WorkflowSerializer, WorkflowStageSerializer, WorkflowTransitionSerializer, StagePermissionSerializer
from auth.roles.permissions import HasAppPermission

# Workflow views (from previous response)
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def workflow_list(request):
    workflows = Workflow.objects.all()
    serializer = WorkflowSerializer(workflows, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def workflow_create(request):
    serializer = WorkflowSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def workflow_update(request, pk):
    try:
        workflow = Workflow.objects.get(pk=pk)
    except Workflow.DoesNotExist:
        return Response({"detail": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WorkflowSerializer(workflow, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def workflow_delete(request, pk):
    try:
        workflow = Workflow.objects.get(pk=pk)
    except Workflow.DoesNotExist:
        return Response({"detail": "Workflow not found"}, status=status.HTTP_404_NOT_FOUND)
    workflow.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# WorkflowStage views
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def workflow_stage_list(request):
    stages = WorkflowStage.objects.all()
    serializer = WorkflowStageSerializer(stages, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def workflow_stage_create(request):
    serializer = WorkflowStageSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def workflow_stage_update(request, pk):
    try:
        stage = WorkflowStage.objects.get(pk=pk)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "Workflow stage not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WorkflowStageSerializer(stage, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def workflow_stage_delete(request, pk):
    try:
        stage = WorkflowStage.objects.get(pk=pk)
    except WorkflowStage.DoesNotExist:
        return Response({"detail": "Workflow stage not found"}, status=status.HTTP_404_NOT_FOUND)
    stage.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# WorkflowTransition views
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def workflow_transition_list(request):
    transitions = WorkflowTransition.objects.all()
    serializer = WorkflowTransitionSerializer(transitions, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def workflow_transition_create(request):
    serializer = WorkflowTransitionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def workflow_transition_update(request, pk):
    try:
        transition = WorkflowTransition.objects.get(pk=pk)
    except WorkflowTransition.DoesNotExist:
        return Response({"detail": "Workflow transition not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = WorkflowTransitionSerializer(transition, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def workflow_transition_delete(request, pk):
    try:
        transition = WorkflowTransition.objects.get(pk=pk)
    except WorkflowTransition.DoesNotExist:
        return Response({"detail": "Workflow transition not found"}, status=status.HTTP_404_NOT_FOUND)
    transition.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# StagePermission views
@permission_classes([HasAppPermission('workflows', 'view')])
@api_view(['GET'])
def stage_permission_list(request):
    permissions = StagePermission.objects.all()
    serializer = StagePermissionSerializer(permissions, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('workflows', 'create')])
@api_view(['POST'])
def stage_permission_create(request):
    serializer = StagePermissionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'update')])
@api_view(['PUT'])
def stage_permission_update(request, pk):
    try:
        permission = StagePermission.objects.get(pk=pk)
    except StagePermission.DoesNotExist:
        return Response({"detail": "Stage permission not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = StagePermissionSerializer(permission, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('workflows', 'delete')])
@api_view(['DELETE'])
def stage_permission_delete(request, pk):
    try:
        permission = StagePermission.objects.get(pk=pk)
    except StagePermission.DoesNotExist:
        return Response({"detail": "Stage permission not found"}, status=status.HTTP_404_NOT_FOUND)
    permission.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)