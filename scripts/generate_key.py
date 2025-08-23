#!/usr/bin/env python3
import secrets

def generate_secret_key():
    """Generate a secure secret key suitable for Flask applications"""
    return secrets.token_hex(32)

if __name__ == '__main__':
    print("Generated Secret Key:", generate_secret_key())
