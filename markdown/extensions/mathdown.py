import markdown
import re
import logging

def build_url(label, base, end):
    """ Build a url from the label, a base, and an end. """
    clean_label = re.sub(r'([ ]+_)|(_[ ]+)|([ ]+)', '_', label)
    return '%s%s%s'% (base, clean_label, end)


class MathdownExtension(markdown.Extension):
    def __init__(self, configs):
        # set extension defaults
        self.config = {
                        'base_url' : ['/', 'String to append to beginning or URL.'],
                        'end_url' : ['/', 'String to append to end of URL.'],
                        'html_class' : ['wikilink', 'CSS hook. Leave blank for none.'],
                        'build_url' : [build_url, 'Callable formats URL from label.'],
        }
        
        # Override defaults with user settings
        for key, value in configs :
            self.setConfig(key, value)
        
    def extendMarkdown(self, md, md_globals):
        self.md = md
    
        # append to end of inline patterns
        MATHDOWN_RE = r'\$([^$]*)\$'
        mathdownPattern = Mathdown(MATHDOWN_RE, self.config)
        mathdownPattern.md = md
        md.preprocessors.add("mathdown", MathdownPreprocessor(self), "_begin")
        md.inlinePatterns.add('mathdown', mathdownPattern, "<not_strong")


class Mathdown(markdown.inlinepatterns.Pattern):
    def __init__(self, pattern, config):
        markdown.inlinepatterns.Pattern.__init__(self, pattern)
        self.config = config
  
    def handleMatch(self, m):
        a = markdown.util.etree.Element("span")
        a.text = '$%s$' % m.group(2)
        return a

class MathdownPreprocessor(markdown.preprocessors.Preprocessor):
    def run(self, lines):
        def repl(matchobj):
            src = matchobj.group(1)
            src = src.replace('\\', '\\\\')
            return '$%s$' % src
        return re.sub('\\$((?:[^\\$\\\\]|\\\\.)*)\\$', repl, '\n'.join(lines)).split('\n')


def makeExtension(configs=None) :
    return MathdownExtension(configs=configs)


if __name__ == "__main__":
    import doctest
    doctest.testmod()


