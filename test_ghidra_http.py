import requests

r = requests.get("http://127.0.0.1:8080/get_current_address")
print("current_address:", r.text)
