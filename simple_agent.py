import logging
from strands import Agent

#logging.basicConfig(level=logging.DEBUG)

agent = Agent(system_prompt="You are a game master for a Dungeon & Dragon game")

agent("Hi, I am an adventurer ready for adventure!")
