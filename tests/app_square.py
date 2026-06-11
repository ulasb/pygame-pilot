"""Minimal pygame app used by the harness tests: a square that moves
with the arrow keys (held state) and teleports home on Return (event)."""

import pygame

pygame.init()
screen = pygame.display.set_mode((200, 150))
pygame.display.set_caption("pilot-test-square")
clock = pygame.time.Clock()

x, y = 100, 75
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            x, y = 100, 75
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        x -= 2
    if keys[pygame.K_RIGHT]:
        x += 2
    if keys[pygame.K_UP]:
        y -= 2
    if keys[pygame.K_DOWN]:
        y += 2
    screen.fill((20, 20, 40))
    pygame.draw.rect(screen, (255, 200, 60), (x - 8, y - 8, 16, 16))
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
