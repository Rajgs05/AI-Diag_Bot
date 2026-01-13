from diagrams import Diagram, Cluster
from diagrams.aws.database import RDS
from diagrams.aws.network import ELB, VPC
from diagrams.aws.compute import EC2
from diagrams.aws.storage import S3

diag = Diagram("AWS Architecture Diagram", filename="output/diagram_1768238007", outformat="dot", show=False)
with diag:
    with Cluster("VPC"):
        elb = ELB("External ELB")
        ec2 = EC2("Webserver")
        rds = RDS("Database")
        ec2 >> rds
        elb >> ec2
    with Cluster("Database Subnet"):
        pass
    s3 = S3("S3 Bucket")
    ec2 >> s3