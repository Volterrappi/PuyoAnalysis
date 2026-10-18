from pathlib import Path
import sys,unittest,io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'puyo_tools'))
from PIL import Image,ImageDraw,ImageFilter
from common.image_board import recognize_board, _sample_board_cell

COLORS={'R':(225,45,65),'B':(45,95,225),'G':(45,190,85),'Y':(245,185,40),
        'P':(185,55,205),'O':(180,185,190)}


def field(size=32,rows=12,bg=(30,35,50)):
    return Image.new('RGB',(size*6,size*rows),bg)


def puyo(image,size,col,row,label):
    d=ImageDraw.Draw(image);x=col*size;y=row*size
    d.ellipse((x+.10*size,y+.08*size,x+.90*size,y+.94*size),fill=COLORS[label])
    for eye in (.30,.55):
        d.ellipse((x+eye*size,y+.22*size,x+(eye+.15)*size,y+.43*size),fill='white')


class ImageBackgroundTests(unittest.TestCase):
    def test_cross_is_empty_but_real_puyo_at_cross_is_not_erased(self):
        for size in (16,28,48):
            image=field(size);d=ImageDraw.Draw(image);x=2*size
            for color in ((220,45,55),(235,235,235)):
                for width in (max(1,size//16),max(2,size//9)):
                    image=field(size);d=ImageDraw.Draw(image)
                    d.line((x+.2*size,.2*size,x+.8*size,.8*size),fill=color,width=width)
                    d.line((x+.8*size,.2*size,x+.2*size,.8*size),fill=color,width=width)
                    self.assertEqual(recognize_board(image,(0,0,*image.size))[1][2],'.',(size,color,width))
            for label in COLORS:
                image=field(size);puyo(image,size,2,0,label)
                self.assertEqual(recognize_board(image,(0,0,*image.size))[1][2],label,(size,label))

    @unittest.skipUnless(all((Path(__file__).parent/'fixtures'/f'cross-marker-{i}.png').exists() for i in range(1,5)), 'Optional local screenshot fixtures are not distributed')
    def test_supplied_rotating_cross_examples_are_excluded(self):
        boxes=((56,20,116,80),(20,16,84,80),(24,22,84,84),(24,30,84,94))
        for i,box in enumerate(boxes,1):
            with Image.open(Path(__file__).parent/'fixtures'/f'cross-marker-{i}.png') as original:
                for dx in (-2,0,2):
                    bounds=(box[0]+dx,box[1],box[2]+dx,box[3])
                    self.assertEqual(_sample_board_cell(original.convert('RGB'),*bounds,cross_cell=True),'.',(i,dx))
                tile=original.crop(box)
                for size in (16,28,48):
                    image=field(size);image.paste(tile.resize((size,size)),(2*size,0))
                    self.assertEqual(recognize_board(image,(0,0,*image.size))[1][2],'.',(i,size))

    def test_strict_red_rule_applies_only_to_column3_row12(self):
        for rows in (12,13):
            image=field(32,rows);offset=rows-12
            for col in (1,2):
                d=ImageDraw.Draw(image);x=col*32;y=offset*32
                d.ellipse((x+3,y+3,x+29,y+30),fill=COLORS['R'])
            result=recognize_board(image,(0,0,*image.size),rows)
            self.assertEqual(result[1][1],'R')
            self.assertEqual(result[1][2],'.')
            puyo(image,32,2,offset,'R')
            self.assertEqual(recognize_board(image,(0,0,*image.size),rows)[1][2],'R')

    def test_colored_and_neutral_backgrounds_are_empty(self):
        for background in ((70,50,100),(35,100,155),(150,90,60),(130,130,130)):
            image=field(bg=background)
            self.assertTrue(all(row=='......' for row in recognize_board(image,(0,0,*image.size))))

    def test_mixed_board_eyes_compression_and_13_row_coordinates(self):
        for rows in (12,13):
            image=field(32,rows,bg=(45,55,85))
            for col,label in enumerate(COLORS):puyo(image,32,col,rows-1,label)
            image=image.filter(ImageFilter.GaussianBlur(.45))
            data=io.BytesIO();image.save(data,format='JPEG',quality=75);data.seek(0)
            with Image.open(data) as compressed:result=recognize_board(compressed,(0,0,*compressed.size),rows)
            self.assertEqual(result[-1],'RBGYPO')
            self.assertTrue(all(row=='......' for row in result[:-1]))


if __name__=='__main__':unittest.main()
