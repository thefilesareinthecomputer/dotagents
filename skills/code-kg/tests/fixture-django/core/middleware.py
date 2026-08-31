"""Request middleware, wired via the MIDDLEWARE settings string."""


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = getattr(request.user, "org", None)
        return self.get_response(request)
