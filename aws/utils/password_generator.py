import random, string
import pulumi

# def password_generator(x):
#     return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(x))

class Password:
    def __init__(self):
        self.dbPassword = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(13))

        # pulumi.export("test", self.dbPassword)