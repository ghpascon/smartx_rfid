from smartx_rfid.db import DatabaseManager
from smartx_rfid.models.license import License

# public_key_path = "license_files/public_key.pem"
# private_key_path = "license_files/private_key.pem"
# with open(public_key_path, "r") as f:
#     public_pem = f.read()
# with open(private_key_path, "r") as f:
#     private_pem = f.read()

public_pem = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA00QgDyPjuscTBoWBnS1p
GReG6ysiK8eEel0BRGp4gv825GJf4LQkhdKXU78f+dh9cxIYKOlHOa2xXyTCHX2s
RbYIqaDxyop3tVoH+hZcB7oxijiyxhEYrm5Ev5Mh54nALAaP6FZJl+YHiX5OOgTu
5enor/YiYXnftzybd2S8Z6wGCDEmyRjZm03+OD3kJhuEC3l8vS6Iq0rl57CC0Jw8
2qrLJeWr6WFdQUJ6BnXjg4foA6wXdteNDU8ARh/whbd6ie3qHZzhcCncgNZqok4O
jjjIWQzhSOtKxg3DywiKAT0LIh9QReMIzLxcoSqi2LMgLbJANcrexsiJUeHEYx/l
oQIDAQAB
-----END PUBLIC KEY-----"""
private_pem = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDTRCAPI+O6xxMG
hYGdLWkZF4brKyIrx4R6XQFEaniC/zbkYl/gtCSF0pdTvx/52H1zEhgo6Uc5rbFf
JMIdfaxFtgipoPHKine1Wgf6FlwHujGKOLLGERiubkS/kyHnicAsBo/oVkmX5geJ
fk46BO7l6eiv9iJhed+3PJt3ZLxnrAYIMSbJGNmbTf44PeQmG4QLeXy9LoirSuXn
sILQnDzaqssl5avpYV1BQnoGdeODh+gDrBd2140NTwBGH/CFt3qJ7eodnOFwKdyA
1mqiTg6OOMhZDOFI60rGDcPLCIoBPQsiH1BF4wjMvFyhKqLYsyAtskA1yt7GyIlR
4cRjH+WhAgMBAAECggEAAdHVgBs3jQe7DZMZA8NfmJi17SN+kx+Vaoz6UQuvo4AK
3y6W+8dXb3DkpBMKdadNr3qbhfTaQS2dIGLPhSEh3/Tr0ri1I8ZGVnk6xiawRseD
IYPK9pG7VitzA4P9w99BOMvawatmbWonfKxfedMqLYV9TzsvWSqLYLot7rTvGmo6
OwX8c9DsQi309tFKuWhjPWb9YzvQSuK/66SqieMQ9NmbhjsCMPSHotQKYAg3aO25
stvhSz0cxGIwcQLStV6Lj/r8mxRjBJ4egxzevULSimlvJaVo9x/sIgopA2zXztn1
R06HkpKciTdznYxgFILwmFrjSU5M6fdLKzdHPgY2AQKBgQD8t6Oc+7+aK+Yf+xXX
csVwY31AHmiO1T+gdoER0U2YJpmrwnA9j+I3jFIQTK6/pw+3qeHuqWWo8QZFEcBz
QbiKEq5l/yNO89HFJDB1jMl56Yx+6+uNUCIyapG8GcrmkAgS22Odypjw1sbd9HmC
875+4F1p/jsrX2kQCuUmY047AQKBgQDWAqX7f1gGAnR0RA0Je4zinHVOqz+LQgvt
EIwX55eA7E/DxE6f9beulOVJAuThkDLbToUgnRzHV6rMXcJXVpHG6QoOgXBpDZ1a
pqctWHWBkwtnY1W3FkSIa9RKUgU7C6ZiXSMPGBWiilvNCcyNHr3NBIMY7aCWy+l4
YoO8il7KoQKBgEV8qPwtLI3TrD725xaKdEdm07WhptY/RHN2oh6oElHXq0FTAVGs
EmN7rcTVkOcZpHS3vWvGIDHHtBWhv+zxETDF2jYpZSf8Wp1+SeTIhU2ELiFn9Six
8/Uw4El8PhIPYGju8gEdB9iQ9bVp109ufd6dCpJuWQ6f+V9z33YisAwBAoGALQZJ
nWvhPQJvNbbLd19C+LoqA+8LY2T11V5R2wWiXkFZVrqKQCUWC+jPhFjThpEr4e/X
GlFzqIzNJknjhTR1Xv/QWdTprXBr1pKRQX0G28fv8kR32BkbOghVlX1EFHQTAUbP
BXHvu06Ymb6iBl6dV/DHFAuKaa9k4yr2xEfoQYECgYEA7iTkZsYXZ+6X/1ImJAt7
RvzrMu4G0GfSmNJ1FU8Pd7iX2cOdpXdw12NbMEp4ovf7HHYfqhi6cFH+FC799Llj
QbYWfPUAGuvsNMoQSsUhKi+eoZyeKYmd2v2Z7SxkceslUN6IKeM2PD5HAmafqP9j
4clPs3vhyWo1tpRk4pUNXLI=
-----END PRIVATE KEY-----"""

db = DatabaseManager("mysql+pymysql://root:admin@localhost:3306/orders")
db.initialize()
db.register_models(License)
db.create_tables()
with db.get_session() as session:
    license_entry = License(public_key=public_pem, private_key=private_pem)
    session.add(license_entry)
