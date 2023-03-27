import requests

host = "http://localhost:8000"
# host = "https://test.myabf.com.au"

headers = {"key": "PROD_uT2}nr1$DS2tNXh1RAR8L)sU0jxPAVf9Lg)", "accept": "*/*"}
# headers = {"key": "test_2xfYE)!ziO4s8Un6zz}vL56UY^KQh-h67Yq", "accept": "*/*"}

# Test key is valid
url = f"{host}/api/cobalt/keycheck/v1.0"
response = requests.get(url, headers=headers)
print(response)

# Send file
url = f"{host}/api/cobalt/sms-file-upload/v1.0"

files = {"filexx": open("utils/sms_cli.txt", "rb")}
values = {
    "filexx": "file.txt",
}
response = requests.post(url, files=files, data=values, headers=headers)

print(response.request.url)
print(response.request.body)
print(response.request.headers)
print(response.reason)
print(response.content)
