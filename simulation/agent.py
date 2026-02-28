import torch
import torch.optim as optim
import random
import numpy as np
from collections import deque
from model import DQN

class Agent:
    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=2000) # Short term memory
        self.gamma = 0.95    # Discount rate (Care about future rewards?)
        self.epsilon = 1.0   # Exploration rate (Start curious)
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        
        self.model = DQN(state_size, action_size)
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        self.criterion = torch.nn.MSELoss()

    def remember(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state):
        # Exploration: Random Move
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)
        
        # Exploitation: Use Brain
        state_tensor = torch.FloatTensor(state)
        act_values = self.model(state_tensor)
        return torch.argmax(act_values).item()

    def replay(self, batch_size):
        if len(self.memory) < batch_size:
            return
        
        minibatch = random.sample(self.memory, batch_size)
        
        for state, action, reward, next_state, done in minibatch:
            target = reward
            if not done:
                next_state_tensor = torch.FloatTensor(next_state)
                target = reward + self.gamma * torch.max(self.model(next_state_tensor)).item()
            
            state_tensor = torch.FloatTensor(state)
            target_f = self.model(state_tensor)
            
            # Update the value for the action we took
            target_f_clone = target_f.clone().detach() # Avoid pytorch error
            target_f_clone[action] = target
            
            # Train the network
            self.optimizer.zero_grad()
            loss = self.criterion(target_f, target_f_clone)
            loss.backward()
            self.optimizer.step()

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            
    def save(self, name):
        torch.save(self.model.state_dict(), name)
        
    def load(self, name):
        self.model.load_state_dict(torch.load(name))