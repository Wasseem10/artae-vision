# Shared and integration packages

The Artae Labs client lives here because it is an integration boundary that a CLI
uses today and a future API or background worker can reuse. Other code belongs here
only when it has multiple real consumers, such as generated contracts shared by the
web and API applications. Inference code remains inside its service so ownership
and deployment boundaries stay clear.
