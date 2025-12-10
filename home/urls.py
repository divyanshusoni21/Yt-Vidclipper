from .views import ClipRequestViewSet
from rest_framework.routers import DefaultRouter
from django.urls import path,include


router = DefaultRouter()
router.register('clip-request', ClipRequestViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
