from rembg import remove
from PIL import Image

def remove_front(input_path:str,output_path:str):
    input_image = Image.open(input_path)
    output_image = remove(input_image)
    output_image.save(output_path)
