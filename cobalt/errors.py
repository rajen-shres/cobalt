from django.shortcuts import render


def not_found_404(request, exception):
    print("404")
    print(exception)
    # try:
    #     if "cobalt_error_msg" in exception:
    #         print("ok")
    #         error = exception["cobalt_error_msg"]
    #     else:
    #         error = None
    # except Exception as e:
    #     print(e)
    error = None

    return render(request, "errors/404.html", {"error": error})


# def server_error_500(request):
#     print("500")
#     return render(request, "errors/500.html")


def server_error_500(request):
    response = render(request, "errors/500.html")
    response.status_code = 500
    return response


def permission_denied_403(request, exception):
    print("403")
    return render(request, "errors/500.html")


def bad_request_400(request, exception):
    print("400")
    return render(request, "errors/500.html")
