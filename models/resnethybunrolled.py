#Hybrid ResNet - BasicBlock - binary block of 2 conv layers, BasicBlock2 - full-precision block of 2 conv layers. 
import torch.nn as nn
import torch
import torch.nn.functional as F
import pdb

__all__ = ['resnethybunrolled']

class BinActive(torch.autograd.Function):
    '''
    Binarize the input activations and calculate the mean across channel dimension.
    '''
    def forward(self, input):
        self.save_for_backward(input)
        size = input.size()
        mean = torch.mean(input.abs(), 1, keepdim=True)
        input = input.sign()
        return input, mean

    def backward(self, grad_output, grad_output_mean):
        input, = self.saved_tensors
		#x = torch.tanh(2*input)
		#y = x**2
		#z = y.mul(-1).add(1)
		#z = z.mul(2)
		#z = torch.exp(-torch.abs(4*input))
		#grad_input = grad_output.mul(z)
        grad_input = grad_output.clone()
        grad_input[input.ge(1)] = 0
        grad_input[input.le(-1)] = 0
        return grad_input

class BinActive2(torch.autograd.Function):
	''' Make the input activations k-bit '''
	def forward(self, input):
		self.save_for_backward(input)
		size = input.size()
		mean = torch.mean(input.abs(), 1, keepdim=True)
		x = input
		#print('x before', x[0][0])
		xmax = x.abs().max()
		num_bits=2 #Bit-precision
		v0 = 1
		v1 = 2
		v2 = -0.5
		#x = x.div(xmax)
		y = 2.**num_bits - 1.
		x = x.add(v0).div(v1)
		x = x.mul(y).round_()
		x = x.div(y)
		x = x.add(v2)
		x = x.mul(v1)
		input = x

		return input, mean

	def backward(self, grad_output, grad_output_mean):
		input, = self.saved_tensors
		#x = torch.tanh(2*input)
		#y = x**2
		#z = y.mul(-1).add(1)
		#z = z.mul(2)
		#z = torch.exp(-torch.abs(4*input))
		#grad_input = grad_output.mul(z)
		grad_input = grad_output.clone()
		#grad_input[input.ge(1)] = 0
		#grad_input[input.le(-1)] = 0
		return grad_input

class BinConv2d(nn.Module):
	def __init__(self, input_channels, output_channels,
			kernel_size=-1, stride=-1, padding=-1, dropout=0):
		super(BinConv2d, self).__init__()
		self.layer_type = 'BinConv2d'
		self.kernel_size = kernel_size
		self.stride = stride
		self.padding = padding
		self.dropout_ratio = dropout

		self.bn = nn.BatchNorm2d(input_channels, eps=1e-4, momentum=0.1, affine=True)
		if dropout!=0:
			self.dropout = nn.Dropout(dropout)
		self.conv = nn.Conv2d(input_channels, output_channels,
				kernel_size=kernel_size, stride=stride, padding=padding)
		# self.relu = nn.ReLU(inplace=True)
    
	def forward(self, x):
		x = self.bn(x)
		# x, mean = BinActive()(x)
		x, mean = BinActive.apply(x)

		if self.dropout_ratio != 0:
			x = self.dropout(x)

		x = self.conv(x)

		#x = self.relu(x)
		return x


class BinConv2d2(nn.Module):
	def __init__(self, input_channels, output_channels,
			kernel_size=-1, stride=-1, padding=-1, dropout=0):
		super(BinConv2d2, self).__init__()
		self.layer_type = 'BinConv2d'
		self.kernel_size = kernel_size
		self.stride = stride
		self.padding = padding
		self.dropout_ratio = dropout

		self.bn = nn.BatchNorm2d(input_channels, eps=1e-4, momentum=0.1, affine=True)

		if dropout!=0:
			self.dropout = nn.Dropout(dropout)

		self.conv = nn.Conv2d(input_channels, output_channels,
				kernel_size=kernel_size, stride=stride, padding=padding)
		# self.relu = nn.ReLU(inplace=True)
    
	def forward(self, x):
		x = self.bn(x)
		# x, mean = BinActive2()(x)
		x, mean = BinActive2.apply(x)
		if self.dropout_ratio!=0:
			x = self.dropout(x)

		x = self.conv(x)

		#x = self.relu(x)
		return x

class BasicBlock(nn.Module):
	expansion = 1

	def __init__(self, input_channels, output_channels, kernel_size = 3,stride=1, padding=1,downsample=None):
		super(BasicBlock, self).__init__()

		self.conv1 = BinConv2d(input_channels, output_channels, kernel_size=3,stride=stride,padding=1,dropout=0)
		self.bn1 = nn.BatchNorm2d(output_channels)
		# self.resconv = nn.Conv2d(input_channels, output_channels, kernel_size=1,stride=stride,padding=0)
		# self.bnres = nn.BatchNorm2d(output_channels)
		self.relu = nn.ReLU(inplace=True)
		self.conv2 = BinConv2d(output_channels, output_channels, kernel_size=3,stride=1,padding=1,dropout=0)
		self.bn2 = nn.BatchNorm2d(output_channels)
		self.downsample = downsample
		#self.do_bntan=do_bntan;
		self.stride = stride

	def forward(self, x):
		residual = x
		out = self.conv1(x)
		out = self.bn1(out)

		if self.downsample is not None:
			#if residual.data.max()>1:
			#    import pdb; pdb.set_trace()
			residual = self.downsample(residual)
			#out +=residual

		out = F.relu(out)
		# residual = self.bnres(self.resconv(residual))
		out += residual
		residual2 = out
		out = self.conv2(out)
		out = self.bn2(out)
		# if self.downsample is not None:
			#if residual.data.max()>1:
			# import pdb; pdb.set_trace()
			# residual = self.downsample(residual)

		out +=residual2 
		out = F.relu(out)
		# out +=residual2
		return out

	

class ResNet(nn.Module):
	def __init__(self):
		super(ResNet, self).__init__()

	def _make_layer(self, block, planes, blocks, stride=1, do_binary=True):
		downsample = None
		downsample1 = None
		if stride != 1 or self.inplanes != planes * block.expansion:
			downsample = nn.Sequential(
				BinConv2d(self.inplanes, planes * block.expansion,
							kernel_size=1, stride=stride,padding=0,dropout=0),
				nn.BatchNorm2d(planes * block.expansion),
			)
			downsample1 = nn.Sequential(
				# nn.Dropout(0.3),
				nn.Conv2d(self.inplanes, planes * block.expansion,
							kernel_size=1, stride=stride,padding=0),
				nn.BatchNorm2d(planes * block.expansion),
			)

		layers = []
		#print('Downsample at layers creation', downsample)
		if do_binary:
			layers.append(block(self.inplanes, planes, 1,stride, 0, downsample))
		else:
			layers.append(block(self.inplanes, planes, 1, stride, 0, downsample1))
		#layers.append(block(self.inplanes, planes,  1, stride, 0, downsample ))
		self.inplanes = planes * block.expansion
		for i in range(1, blocks-1):
			layers.append(block(self.inplanes, planes))
		layers.append(block(self.inplanes, planes))
		return nn.Sequential(*layers)

	def forward(self, x):
		x = self.conv1(x)
		x = self.bn1(x)
		x = self.relu1(x)
		residual1 = x.clone() 
		out = x.clone() 
		out = self.conv2(out)
		out = self.bn2(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv3(out)
		out = self.bn3(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv4(out)
		out = self.bn4(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv5(out)
		out = self.bn5(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv6(out)
		out = self.bn6(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv7(out)
		out = self.bn7(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv8(out)
		out = self.bn8(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv9(out)
		out = self.bn9(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv10(out)
		out = self.bn10(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv11(out)
		out = self.bn11(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		#########Layer################ 
		out = self.conv12(out)
		out = self.bn12(out)
		residual1 = self.resconv1(residual1)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv13(out)
		out = self.bn13(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv14(out)
		out = self.bn14(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv15(out)
		out = self.bn15(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv16(out)
		out = self.bn16(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv17(out)
		out = self.bn17(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv18(out)
		out = self.bn18(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv19(out)
		out = self.bn19(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv20(out)
		out = self.bn20(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv21(out)
		out = self.bn21(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		#########Layer################ 
		out = self.conv22(out)
		out = self.bn22(out)
		residual1 = self.resconv2(residual1)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv23(out)
		out = self.bn23(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv24(out)
		out = self.bn24(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv25(out)
		out = self.bn25(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv26(out)
		out = self.bn26(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv27(out)
		out = self.bn27(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv28(out)
		out = self.bn28(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv29(out)
		out = self.bn29(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv30(out)
		out = self.bn30(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		out = self.conv31(out)
		out = self.bn31(out)
		out = F.relu(out)
		out = out + residual1
		residual1 = out.clone() 
		################################### 
		#########Layer################ 
		x=out 
		x = self.avgpool(x)

		x = x.view(x.size(0), -1)

		x = self.bn32(x)

		x = self.fc(x)

		x = self.bn33(x)

		# x = self.logsoftmax(x)
		x = self.logsoftmax(x)

		return x

class ResNet_cifar100(ResNet):
	def __init__(self, num_classes=100,
					block=BasicBlock, depth=18):
		super(ResNet_cifar100, self).__init__()
		self.inflate = 1
		self.inplanes = 16*self.inflate
		n = int((depth) / 6)+2
		# The layers with binary activations are defined as BinConv2d whereas layers with multi-bit activations are defined as BinConv2d2
		self.conv1=nn.Conv2d(3,int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn1= nn.BatchNorm2d(int(16*self.inflate))
		self.relu1=nn.ReLU(inplace=True)
		self.conv2=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn2= nn.BatchNorm2d(int(16*self.inflate))
		self.relu2=nn.ReLU(inplace=True)
		#######################################################

		self.conv3=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn3= nn.BatchNorm2d(int(16*self.inflate))
		self.relu3=nn.ReLU(inplace=True)
		#######################################################

		self.conv4=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn4= nn.BatchNorm2d(int(16*self.inflate))
		self.relu4=nn.ReLU(inplace=True)
		#######################################################

		self.conv5=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn5= nn.BatchNorm2d(int(16*self.inflate))
		self.relu5=nn.ReLU(inplace=True)
		#######################################################

		self.conv6=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn6= nn.BatchNorm2d(int(16*self.inflate))
		self.relu6=nn.ReLU(inplace=True)
		#######################################################

		self.conv7=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn7= nn.BatchNorm2d(int(16*self.inflate))
		self.relu7=nn.ReLU(inplace=True)
		#######################################################

		self.conv8=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn8= nn.BatchNorm2d(int(16*self.inflate))
		self.relu8=nn.ReLU(inplace=True)
		#######################################################

		self.conv9=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn9= nn.BatchNorm2d(int(16*self.inflate))
		self.relu9=nn.ReLU(inplace=True)
		#######################################################

		self.conv10=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn10= nn.BatchNorm2d(int(16*self.inflate))
		self.relu10=nn.ReLU(inplace=True)
		#######################################################

		self.conv11=BinConv2d(int(16*self.inflate), int(16*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn11= nn.BatchNorm2d(int(16*self.inflate))
		self.relu11=nn.ReLU(inplace=True)
		#######################################################

		#########Layer################ 
		self.conv12=BinConv2d(int(16*self.inflate), int(32*self.inflate), kernel_size=3, stride=2, padding=1)
		self.bn12= nn.BatchNorm2d(int(32*self.inflate))
		self.resconv1=nn.Sequential(BinConv2d(int(16*self.inflate), int(32*self.inflate), kernel_size=1, stride=2, padding=0),
		nn.BatchNorm2d(int(32*self.inflate)),
		nn.ReLU(inplace=True),)
		self.relu12=nn.ReLU(inplace=True)
		#######################################################

		self.conv13=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn13= nn.BatchNorm2d(int(32*self.inflate))
		self.relu13=nn.ReLU(inplace=True)
		#######################################################

		self.conv14=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn14= nn.BatchNorm2d(int(32*self.inflate))
		self.relu14=nn.ReLU(inplace=True)
		#######################################################

		self.conv15=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn15= nn.BatchNorm2d(int(32*self.inflate))
		self.relu15=nn.ReLU(inplace=True)
		#######################################################

		self.conv16=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn16= nn.BatchNorm2d(int(32*self.inflate))
		self.relu16=nn.ReLU(inplace=True)
		#######################################################

		self.conv17=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn17= nn.BatchNorm2d(int(32*self.inflate))
		self.relu17=nn.ReLU(inplace=True)
		#######################################################

		self.conv18=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn18= nn.BatchNorm2d(int(32*self.inflate))
		self.relu18=nn.ReLU(inplace=True)
		#######################################################

		self.conv19=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn19= nn.BatchNorm2d(int(32*self.inflate))
		self.relu19=nn.ReLU(inplace=True)
		#######################################################

		self.conv20=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn20= nn.BatchNorm2d(int(32*self.inflate))
		self.relu20=nn.ReLU(inplace=True)
		#######################################################

		self.conv21=BinConv2d(int(32*self.inflate), int(32*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn21= nn.BatchNorm2d(int(32*self.inflate))
		self.relu21=nn.ReLU(inplace=True)
		#######################################################

		#########Layer################ 
		self.conv22=BinConv2d2(int(32*self.inflate), int(64*self.inflate), kernel_size=3, stride=2, padding=1)
		self.bn22= nn.BatchNorm2d(int(64*self.inflate))
		self.resconv2=nn.Sequential(BinConv2d2(int(32*self.inflate), int(64*self.inflate), kernel_size=1, stride=2, padding=0),
		nn.BatchNorm2d(int(64*self.inflate)),
		nn.ReLU(inplace=True),)
		self.relu22=nn.ReLU(inplace=True)
		#######################################################

		self.conv23=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn23= nn.BatchNorm2d(int(64*self.inflate))
		self.relu23=nn.ReLU(inplace=True)
		#######################################################

		self.conv24=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn24= nn.BatchNorm2d(int(64*self.inflate))
		self.relu24=nn.ReLU(inplace=True)
		#######################################################

		self.conv25=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn25= nn.BatchNorm2d(int(64*self.inflate))
		self.relu25=nn.ReLU(inplace=True)
		#######################################################

		self.conv26=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn26= nn.BatchNorm2d(int(64*self.inflate))
		self.relu26=nn.ReLU(inplace=True)
		#######################################################

		self.conv27=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn27= nn.BatchNorm2d(int(64*self.inflate))
		self.relu27=nn.ReLU(inplace=True)
		#######################################################

		self.conv28=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn28= nn.BatchNorm2d(int(64*self.inflate))
		self.relu28=nn.ReLU(inplace=True)
		#######################################################

		self.conv29=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn29= nn.BatchNorm2d(int(64*self.inflate))
		self.relu29=nn.ReLU(inplace=True)
		#######################################################

		self.conv30=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn30= nn.BatchNorm2d(int(64*self.inflate))
		self.relu30=nn.ReLU(inplace=True)
		#######################################################

		self.conv31=BinConv2d2(int(64*self.inflate), int(64*self.inflate), kernel_size=3, stride=1, padding=1)
		self.bn31= nn.BatchNorm2d(int(64*self.inflate))
		self.relu31=nn.ReLU(inplace=True)
		#######################################################

		#########Layer################ 
		self.avgpool=nn.AvgPool2d(8)
		self.bn32= nn.BatchNorm1d(int(64*self.inflate))
		self.fc=nn.Linear(int(64*self.inflate),num_classes)
		self.bn33= nn.BatchNorm1d(100)
		self.logsoftmax=nn.LogSoftmax()
	

def resnethybunrolled(**kwargs):
    num_classes, depth, dataset = map(
        kwargs.get, ['num_classes', 'depth', 'dataset'])
    if dataset == 'imagenet':
        num_classes = num_classes or 1000
        depth = depth or 50
        if depth == 18:
            return ResNet_imagenet(num_classes=num_classes,
                                   block=BasicBlock, layers=[2, 2, 2, 2])
        if depth == 34:
            return ResNet_imagenet(num_classes=num_classes,
                                   block=BasicBlock, layers=[3, 4, 6, 3])
        if depth == 50:
            return ResNet_imagenet(num_classes=num_classes,
                                   block=Bottleneck, layers=[3, 4, 6, 3])
        if depth == 101:
            return ResNet_imagenet(num_classes=num_classes,
                                   block=Bottleneck, layers=[3, 4, 23, 3])
        if depth == 152:
            return ResNet_imagenet(num_classes=num_classes,
                                   block=Bottleneck, layers=[3, 8, 36, 3])

    elif dataset == 'cifar10':
        num_classes = num_classes or 10
        depth = depth or 18
        return ResNet_cifar10(num_classes=num_classes,
                              block=BasicBlock, depth=depth)
    elif dataset == 'cifar100':
        num_classes = num_classes or 100
        depth = depth or 18
        return ResNet_cifar100(num_classes=num_classes,
                              block=BasicBlock, depth=depth)
