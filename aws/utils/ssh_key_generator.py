import os
import pulumi
import pulumi_tls as tls


class SSHKey:
    def __init__(self):
        self.ssh_key = tls.PrivateKey("ssh-key",
                                 algorithm="RSA",
                                 rsa_bits=4096,
                                 opts=pulumi.ResourceOptions(ignore_changes=["*"])
                                 )

        pulumi.export("public_key_pem", self.ssh_key.public_key_pem)
        pulumi.export("private_key_pem", pulumi.Output.secret(self.ssh_key.private_key_pem))






