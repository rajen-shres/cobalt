import requests

host = "http://localhost:8000"
host = "https://test.myabf.com.au"

headers = {"key": "API_G$h9UM-e_t07W36C^ocCRVuI$l9l1VIwhCl$", "accept": "*/*"}
headers = {"key": "test_2xfYE)!ziO4s8Un6zz}vL56UY^KQh-h67Yq", "accept": "*/*"}

# Test key is valid
url = f"{host}/api/cobalt/keycheck/v1.0"
response = requests.get(url, headers=headers)
print(response)

# Send file
url = f"{host}/api/cobalt/notification-file-upload/v1.0"

files = {"file": open("utils/sms_cli.txt", "rb")}
values = {
    "sender_identification": "12345abc",
}
response = requests.post(url, files=files, data=values, headers=headers)

print(response.request.url)
print(response.request.body)
print(response.request.headers)
print(response.reason)
print(response.content)
