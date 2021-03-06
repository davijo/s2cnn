# pylint: disable=E1101,R,C
import torch
import torch.nn.functional as F
import torchvision

import os
import shutil
import time
import logging
import copy

from dataset import Shrec17, CacheNPY, ToMesh, ProjectOnSphere

from model import Model


def main(log_dir, augmentation, dataset, batch_size, num_workers):
    arguments = copy.deepcopy(locals())

    os.mkdir(log_dir)
    shutil.copy2(__file__, os.path.join(log_dir, "script.py"))

    logger = logging.getLogger("train")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    ch = logging.StreamHandler()
    logger.addHandler(ch)
    fh = logging.FileHandler(os.path.join(log_dir, "log.txt"))
    logger.addHandler(fh)

    logger.info("%s", repr(arguments))

    torch.backends.cudnn.benchmark = True

    # Increasing `repeat` will generate more cached files
    transform = CacheNPY(prefix="b64_", repeat=augmentation, transform=torchvision.transforms.Compose(
        [
            ToMesh(random_rotations=True, random_translation=0.1),
            ProjectOnSphere(bandwidth=64)
        ]
    ))

    def target_transform(x):
        classes = ['02691156', '02747177', '02773838', '02801938', '02808440', '02818832', '02828884', '02843684', '02871439', '02876657',
                   '02880940', '02924116', '02933112', '02942699', '02946921', '02954340', '02958343', '02992529', '03001627', '03046257',
                   '03085013', '03207941', '03211117', '03261776', '03325088', '03337140', '03467517', '03513137', '03593526', '03624134',
                   '03636649', '03642806', '03691459', '03710193', '03759954', '03761084', '03790512', '03797390', '03928116', '03938244',
                   '03948459', '03991062', '04004475', '04074963', '04090263', '04099429', '04225987', '04256520', '04330267', '04379243',
                   '04401088', '04460130', '04468005', '04530566', '04554684']
        return classes.index(x[0])

    train_set = Shrec17("data", dataset, perturbed=True, download=True, transform=transform, target_transform=target_transform)

    train_loader = torch.utils.data.DataLoader(train_set, batch_size=batch_size, shuffle=True, num_workers=num_workers, pin_memory=True, drop_last=True)

    model = Model(55)
    model.load_state_dict(torch.load("state.pkl", map_location="cpu"))
    model.cuda()

    logger.info("{} paramerters in total".format(sum(x.numel() for x in model.parameters())))
    logger.info("{} paramerters in the last layer".format(sum(x.numel() for x in model.out_layer.parameters())))

    optimizer = torch.optim.SGD(model.parameters(), lr=0, momentum=0.9)

    def train_step(data, target):
        model.train()
        data, target = data.cuda(), target.cuda()
        data, target = torch.autograd.Variable(data), torch.autograd.Variable(target)

        prediction = model(data)
        loss = F.nll_loss(prediction, target)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        return loss.data[0]

    def get_learning_rate(epoch):
        limits = [100, 200]
        lrs = [0.5, 0.05, 0.005]
        assert len(lrs) == len(limits) + 1
        for lim, lr in zip(limits, lrs):
            if epoch < lim:
                return lr
        return lrs[-1]

    for epoch in range(300):

        lr = get_learning_rate(epoch)
        logger.info("learning rate = {} and batch size = {}".format(lr, train_loader.batch_size))
        for p in optimizer.param_groups:
            p['lr'] = lr

        total_loss = 0
        for batch_idx, (data, target) in enumerate(train_loader):
            time_start = time.perf_counter()
            loss = train_step(data, target)

            total_loss += loss

            logger.info("[{}:{}/{}] LOSS={:.2} <LOSS>={:.2} time={:.2}".format(
                epoch, batch_idx, len(train_loader), loss, total_loss / (batch_idx + 1), time.perf_counter() - time_start))

        torch.save(model.state_dict(), os.path.join(log_dir, "state.pkl"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("--log_dir", type=str, required=True)
    parser.add_argument("--augmentation", type=int, default=1,
                        help="Generate multiple image with random rotations and translations (recommanded = 3)")
    parser.add_argument("--dataset", choices={"test", "val", "train"}, default="train")
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--num_workers", type=int, default=1)

    args = parser.parse_args()

    main(**args.__dict__)
