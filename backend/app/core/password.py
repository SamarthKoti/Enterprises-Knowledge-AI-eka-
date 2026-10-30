from argon2 import PasswordHasher
hasher = PasswordHasher()

if __name__ == '__main__':
    from getpass import getpass
    password = getpass('Demo password (8 to 12 characters): ')
    if not 8 <= len(password) <= 12:
        raise SystemExit('Demo password must be 8 to 12 characters.')
    print(hasher.hash(password))
