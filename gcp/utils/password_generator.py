import random, string

def password_generator(x):
    return''.join(random.choice(string.ascii_letters + string.digits) for _ in range(x))