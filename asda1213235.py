with open('test/9.bundle', 'rb') as f:
    file_byte = f.read()

with open('test/11.bundle', 'wb') as f:
    f.write(file_byte+(b'\x00' * 10))
