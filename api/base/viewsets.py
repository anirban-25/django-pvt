from rest_framework.exceptions import MethodNotAllowed


class NoListMixin:
    """Mixin that defines List operations as not allowed (for use in conjunction with MultipleDBModelViewSet)."""

    def list(self, request, *args, **kwargs):
        raise MethodNotAllowed(self.action)


class NoCreateMixin:
    """Mixin that defines Create operations as not allowed (for use in conjunction with MultipleDBModelViewSet)."""

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(self.action)


class NoUpdateMixin:
    """Mixin that defines Update operations as not allowed (for use in conjunction with MultipleDBModelViewSet)."""

    def update(self, request, *args, pk=None, **kwargs):
        raise MethodNotAllowed(self.action)

    def partial_update(self, request, *args, pk=None, **kwargs):
        raise MethodNotAllowed(self.action)

    def bulk_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(self.action)

    def partial_bulk_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(self.action)


class NoDestroyMixin:
    """Mixin that defines Destroy operations as not allowed (for use in conjunction with MultipleDBModelViewSet)."""

    def destroy(self, request, *args, pk=None, **kwargs):
        raise MethodNotAllowed(self.action)

    def bulk_destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(self.action)
