from .services import resolve_active_organization


class ActiveOrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = resolve_active_organization(request)
        return self.get_response(request)
