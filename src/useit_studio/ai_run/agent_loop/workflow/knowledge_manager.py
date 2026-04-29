class KnowledgeManager:
    def __init__(self):
        self.knowledge_base = {"general": "You are a helpful assistant for computer use tasks planning."}

    def add_knowledge(self, domain, knowledge):
        self.knowledge_base[domain] = knowledge

    def get_knowledge(self, domain):
        return self.knowledge_base[domain]
