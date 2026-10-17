class ConversationHandler:
    def __init__(self, llm, condense_prompt):
        self.llm = llm
        self.condense_prompt = condense_prompt
        self.chat_history = []
        self.conversational_chain = None

    def set_context(self, chain):
        self.conversational_chain = chain

    def get_response(self, user_input, chat_history=None):
        if chat_history and len(chat_history) > 0:
            history_str = ""
            for human, ai in chat_history:
                history_str += f"Human: {human}\nAI: {ai}\n"
            formatted = self.condense_prompt.format_messages(
                chat_history=history_str,
                input=user_input
            )
            rewritten = self.llm.invoke(formatted).strip()
            user_input = rewritten
        response = self.conversational_chain.invoke({"input": user_input})
        self.chat_history.append((user_input, response["answer"]))
        return response