import wave
import struct
import math
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Audio parameters
sample_rate = 44100
duration = 5  # seconds
frequency = 440  # Hz (A4 note)
num_samples = duration * sample_rate

logger.info(f"Creating WAV file with parameters:")
logger.info(f"Sample rate: {sample_rate} Hz")
logger.info(f"Duration: {duration} seconds")
logger.info(f"Frequency: {frequency} Hz")

# Create WAV file
with wave.open('test3.wav', 'w') as wav_file:
    # Set parameters
    wav_file.setnchannels(1)  # Mono
    wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
    wav_file.setframerate(sample_rate)
    
    logger.info("Writing audio samples...")
    # Generate and write samples
    for i in range(num_samples):
        t = float(i) / sample_rate
        value = int(32767.0 * math.sin(2.0 * math.pi * frequency * t))
        data = struct.pack('<h', value)
        wav_file.writeframes(data)

logger.info("WAV file created successfully")
