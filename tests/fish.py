from pylenium.driver import Pylenium
from pylenium.config import PyleniumConfig

config = PyleniumConfig()
config.driver.browser = "firefox"
# config.driver.browser='opera'
config.driver.options = ["headless"]
py = Pylenium(config)
py.visit("https://qap.dev")
py.get('a[href="/about"]').hover()
py.get('a[href="/leadership"][class^="Header-nav"]').click()
assert py.contains("Carlos Kidman")
