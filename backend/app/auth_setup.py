"""Create the owner password hash:   python -m app.auth_setup

Prints an OWNER_PASSWORD_HASH=... line to paste into backend/.env (or your host's environment settings).
The password itself is never stored or printed."""
import getpass
import sys

from app.auth import MIN_PASSWORD_LENGTH, hash_password


def main() -> None:
    password = getpass.getpass("Choose the owner password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if password != getpass.getpass("Repeat the password: "):
        sys.exit("The passwords did not match.")
    print("\nAdd this line to backend/.env:\n")
    print(f"OWNER_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
