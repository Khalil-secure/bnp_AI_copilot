from strands import Agent
from strands_tools import http_request

agent = Agent(
    tools=[http_request]
    )

agent("""
   Using the website https://en.wikipedia.org/wiki/Dungeons_%26_Dragons tell me the name of the designers of
   Dungeons and Dragons.
    """
    )

