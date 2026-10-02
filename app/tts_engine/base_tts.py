import abc

class BaseTTS:
     @abc.abstractmethod
     def synthesize(self,text:str,voice:str,output_dir:str, language:str=""):
          pass
     
     @abc.abstractmethod
     def release(self):
          pass