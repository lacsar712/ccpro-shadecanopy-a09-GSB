from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = 409
    default_detail = "资源状态冲突"
    default_code = "conflict"
