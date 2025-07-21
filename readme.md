# OSKOLCTF
Таски с ивента Летней ИТ Школы

## task1
Просто откройте код))
Flag: oskolctf{hahaha_really_my_first_ctf}

## task2
Смотрим куки
Flag: oskolctf{ti_uzhe_umniy_esli_reshil_eto}

## task3
```python
import requests
req = requests.post("http://localhost:8337/task3", data="b3Nrb2xjdGY=")
print(req.text)
```
Flag: oskolctf{xorg_worship_zhdet_tebya}

## task4
```python
import requests
req = requests.get("http://localhost:8337/task4", cookies={"xorg_worship_flag_for_you": "true"})
print(req.text)
```
Flag: oskolctf{moya_lubimaya_taska_posle_labirinta}
