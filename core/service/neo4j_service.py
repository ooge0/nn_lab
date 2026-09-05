import configparser
from py2neo import Graph
from loguru import logger


class Neo4jService:
    """
    Service class for managing Neo4j connections and health checks.

    Main Description
    ----------------
    Encapsulates logic for loading credentials, creating a Graph object,
    and verifying that the Neo4j service is reachable via Bolt.

    References
    ----------
    - Neo4j Python driver (py2neo): https://py2neo.org/
    - Neo4j configuration: https://neo4j.com/docs/operations-manual/current/configuration/
    - Bolt protocol: https://neo4j.com/docs/bolt/current/

    Attributes
    ----------
    config_path : str
        Path to the configuration file containing Neo4j credentials.
    """

    def __init__(self, config_path: str = "config/config.ini"):
        """
        Initialize the Neo4jService with a config file path.

        Parameters
        ----------
        config_path : str, optional
            Path to the configuration file (default: "config/config.ini").
        """
        self.config_path = config_path

    def load_neo4j_creds(self) -> Graph:
        """
        Load Neo4j credentials from the config file and return a Graph object.

        Returns
        -------
        Graph
            Authenticated py2neo Graph instance.
        """
        config = configparser.ConfigParser()
        config.read(self.config_path)
        uri = config["neo4j"]["uri"]
        user = config["neo4j"]["user"]
        password = config["neo4j"]["password"]
        return Graph(uri, auth=(user, password))

    def ensure_neo4j_run(self) -> bool:
        """
        Check if the Neo4j service is reachable via Bolt.

        Returns
        -------
        bool
            True if the connection is successful, False otherwise.
        """
        try:
            graph = self.load_neo4j_creds()
            graph.run("RETURN 1").data()
            logger.info("Neo4j connection successful")
            return True
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            return False
