import random
import sys
from enum import Enum, auto

from direct.showbase.ShowBase import ShowBase
from direct.showbase.ShowBaseGlobal import globalClock
from direct.showbase.InputStateGlobal import inputState
from panda3d.bullet import BulletWorld, BulletDebugNode
from panda3d.core import NodePath, TextNode
from panda3d.core import Point2, Point3, Quat, Vec3, LColor, CardMaker
from panda3d.core import TransparencyAttrib
from panda3d.core import load_prc_file_data
from direct.interval.IntervalGlobal import Sequence, Func

from constants import Mask
from walker import Walker, Motions
from scene import Scene
from ball_controller import BallController
from utils import DrawText


load_prc_file_data("", """
    textures-power-2 none
    gl-coordinate-system default
    window-title Panda3D Simulation Environment
    filled-wireframe-apply-shader true
    stm-max-views 8
    stm-max-chunk-count 2048
""")

class Status(Enum):

    PLAY = auto()
    READY = auto()
    SETUP = auto()
    MAKE = auto()


class AvoidBalls(ShowBase):

    def __init__(self):
        super().__init__()
        self.disable_mouse()
        self.world = BulletWorld()
        self.world.set_gravity(0, 0, -9.81)

        self.debug_np = self.render.attach_new_node(BulletDebugNode('debug'))
        self.world.set_debug_node(self.debug_np.node())

        self.scene = Scene(self.world)
        self.scene.reparent_to(self.render)

        self.walker = Walker(self.world)
        self.walker.reparent_to(self.render)

        self.floater = NodePath('floater')
        self.floater.set_z(3.0)
        self.floater.reparent_to(self.walker)

        self.camera.reparent_to(self.walker)
        self.camera.set_pos(self.walker.navigate())
        self.camera.look_at(self.floater)
        self.camLens.set_fov(90)

        self.socre_display = ScoreDisplays()
        self.screen = Screen()
        self.screen.show_start_screen()

        self.ball_controller = BallController(self.world, self.walker, self.socre_display)
        self.timer = 0
        self.state = None

        inputState.watch_with_modifiers('forward', 'arrow_up')
        inputState.watch_with_modifiers('backward', 'arrow_down')
        inputState.watch_with_modifiers('left', 'arrow_left')
        inputState.watch_with_modifiers('right', 'arrow_right')

        self.accept('d', self.toggle_debug)
        self.accept('p', self.print_position)
        self.accept('escape', sys.exit)
        self.taskMgr.add(self.update, 'update')

    def print_position(self):
        print('walker_pos: ', self.walker.get_pos())

    def toggle_debug(self):
        if self.debug_np.is_hidden():
            self.debug_np.show()
        else:
            self.debug_np.hide()

    def ray_cast(self, from_pos, to_pos):
        if (result := self.world.ray_test_closest(
                from_pos, to_pos, Mask.environment)).has_hit():
            return result.get_node()

        return None

    def find_camera_pos(self, walker_pos, next_pos):
        q = Quat()
        point = Point3(0, 0, 0)
        start = self.camera.get_pos()
        angle = r = None

        for i in range(36):
            camera_pos = next_pos + walker_pos
            if self.ray_cast(camera_pos, walker_pos) == self.walker.node():
                return next_pos

            times = i // 2 + 1
            angle = 10 * times if i % 2 == 0 else -10 * times
            q.set_from_axis_angle(angle, Vec3.up())
            r = q.xform(start - point)
            next_pos = point + r

        return None

    def control_camera(self):
        """Reposition the camera if the camera's view is blocked
           by other objects like terrain, rocks, trees.
        """
        walker_pos = self.walker.get_pos()
        camera_pos = self.camera.get_pos() + walker_pos

        if self.ray_cast(camera_pos, walker_pos) != self.walker.node():
            if next_pos := self.find_camera_pos(walker_pos, self.walker.navigate()):
                self.camera.set_pos(next_pos)
                self.camera.look_at(self.floater)

    def control_walker(self, dt):
        motions = []

        if inputState.is_set('forward'):
            motions.append(Motions.FORWARD)
        if inputState.is_set('backward'):
            motions.append(Motions.BACKWARD)
        if inputState.is_set('left'):
            motions.append(Motions.LEFT)
        if inputState.is_set('right'):
            motions.append(Motions.RIGHT)

        self.walker.update(dt, motions)

    def find_walker_start_pos(self):
        for hit in self.world.rayTestAll(
                Point3(0, 0, 30), Point3(0, 0, -30), mask=Mask.terrain).get_hits():

            if hit.get_node() == self.walker.node():
                continue

            pos = hit.get_hit_pos()
            return pos + Vec3(0, 0, 1.5)

    def update(self, task):
        dt = globalClock.get_dt()
        self.control_walker(dt)
        self.control_camera()
        self.ball_controller.update(dt)

        match self.state:

            case Status.PLAY:
                if task.time > self.timer:
                    self.ball_controller.shoot()
                    self.timer = task.time + random.randint(1, 10) / 10

                if self.scene.goal_gate.sensor.finish_line:
                    self.screen.show_switch_screen()
                    self.state = None

            case Status.READY:
                if not self.screen.is_appear:
                    self.state = Status.PLAY

            case Status.SETUP:
                pos = self.find_walker_start_pos()
                self.walker.set_pos(pos)
                self.scene.setup_scene()
                self.screen.hide_screen()
                self.state = Status.READY

            case Status.MAKE:
                if self.scene.update():
                    self.state = Status.SETUP

            case _:
                if self.screen.is_appear:
                    self.state = Status.MAKE

        self.world.do_physics(dt)
        return task.cont


class Screen(NodePath):

    def __init__(self):
        cm = CardMaker('card')
        cm.set_frame_fullscreen_quad()
        super().__init__(cm.generate())
        self.set_transparency(TransparencyAttrib.MAlpha)

        # self.bg = LColor(.95, .95, .95, 1.0)
        self.bg = LColor(1.0, 1.0, 1.0, 1.0)
        self.fg = LColor(.4, .4, .4, 1.0)
        self.is_appear = False

        self.title = DrawText(
            base.aspect2d, TextNode.ACenter, Point2(0, 0), self.fg, .2)

    def switch_screens(self):
        self.is_appear = not self.is_appear

    def show_start_screen(self):
        self.reparent_to(base.render2d)
        self.set_color(self.bg)
        self.switch_screens()
        self.title.setText('Panda3D Simulation Environment')

    def show_switch_screen(self):
        self.title.setText('Change the terrain')

        Sequence(
            Func(lambda: self.title.reparent_to(base.aspect2d)),
            Func(lambda: self.reparent_to(base.render2d)),
            self.colorInterval(2.0, self.bg, self.bg - LColor(0, 0, 0, 1.0)),
            self.title.colorScaleInterval(1.0, self.fg, blendType='easeInOut'),
            Func(self.switch_screens)
        ).start()

    def hide_screen(self):
        Sequence(
            self.title.colorScaleInterval(2.0, self.fg - LColor(0, 0, 0, 1.0), blendType='easeInOut'),
            self.colorInterval(1.0, self.bg - LColor(0, 0, 0, 1.0), self.bg),
            Func(lambda: self.title.detach_node()),
            Func(lambda: self.detach_node()),
            Func(self.switch_screens),
        ).start()


class ScoreDisplays:

    def __init__(self):
        fg = LColor(1, 1, 1, 1)
        scale = 0.1
        parent = base.a2dTopLeft
        align = TextNode.ALeft
        self.avoid = DrawText(parent, align, Point2(0.05, -0.1), fg, scale)
        self.hit = DrawText(parent, align, Point2(0.17, -0.2), fg, scale)
        self.avoid_score = 0
        self.hit_score = 0

    def reset(self):
        self.avoid.setText('')
        self.hit.setText('')

    def add(self, avoid=0, hit=0):
        self.avoid_score += avoid
        self.hit_score += hit

        self.avoid.setText(f'avoid: {self.avoid_score}')
        self.hit.setText(f'hit: {self.hit_score}')


if __name__ == '__main__':
    app = AvoidBalls()
    app.run()