import logging
import re
from backend.config import TARGET_MIN_WORDS, TARGET_MAX_WORDS

logger = logging.getLogger(__name__)

def chunk_text(text: str, min_words: int = None, max_words: int = None) -> list[str]:
    if min_words is None:
        min_words = TARGET_MIN_WORDS
    if max_words is None:
        max_words = TARGET_MAX_WORDS
        
    if not text or not text.strip():
        return ['']
        
    paragraphs = re.split(r'\n\s*\n', text.strip())
    temp_paragraphs = []
    
    for para in paragraphs:
        if not para.strip():
            continue
        words = para.split()
        count = len(words)
        if count > max_words:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                s_words = sentence.split()
                s_count = len(s_words)
                if s_count > max_words:
                    for i in range(0, s_count, max_words):
                        temp_paragraphs.append(' '.join(s_words[i:i+max_words]))
                elif s_count > 0:
                    temp_paragraphs.append(sentence)
        elif count > 0:
            temp_paragraphs.append(para)
            
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    for para in temp_paragraphs:
        count = len(para.split())
        
        if current_word_count + count > max_words and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_word_count = count
        else:
            current_chunk.append(para)
            current_word_count += count
            
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
        
    if len(chunks) > 1:
        last_chunk_words = len(chunks[-1].split())
        if last_chunk_words < min_words / 3:
            last_chunk = chunks.pop()
            chunks[-1] = chunks[-1] + '\n\n' + last_chunk
            
    if not chunks:
        return [text]
        
    return chunks
