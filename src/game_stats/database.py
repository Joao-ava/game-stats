import os
from cassandra.cluster import Cluster

cassandra_host = os.environ.get("CASSANDRA_HOST", "localhost")
cluster = Cluster([cassandra_host])
session = cluster.connect()
