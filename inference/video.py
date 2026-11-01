import os
import cv2
import numpy as np

def loadvideo(filename: str) -> np.ndarray:                                                                                 
      """Load a video as (channels, frames, height, width) float32 array."""
      if not os.path.exists(filename):                                                                                        
          raise FileNotFoundError(filename)
                                                                                                                              
      capture = cv2.VideoCapture(filename)                                                                                    
      frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
      frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))                                                                
      frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                                                                                                                              
      v = np.zeros((frame_count, frame_height, frame_width, 3), np.uint8)                                                     
      for count in range(frame_count):                                                                                        
          ret, frame = capture.read()                                                                                         
          if not ret:
              raise ValueError(f"Failed to load frame #{count} of {filename}.")
          v[count] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)                                                                   
  
      return v.transpose((3, 0, 1, 2))  # (C, F, H, W)
  