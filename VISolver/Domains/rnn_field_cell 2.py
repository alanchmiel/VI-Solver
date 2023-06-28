# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Module for constructing RNN Cells.

## Base interface for all RNN Cells

@@RNNCell

## RNN Cells for use with TensorFlow's core RNN methods

@@BasicRNNCell
@@BasicLSTMCell
@@GRUCell
@@LSTMCell

## Classes storing split `RNNCell` state

@@LSTMStateTuple

## RNN Cell wrappers (RNNCells that wrap other RNNCells)

@@MultiRNNCell
@@DropoutWrapper
@@EmbeddingWrapper
@@InputProjectionWrapper
@@OutputProjectionWrapper
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import math

from tensorflow.python.framework import ops
from tensorflow.python.framework import tensor_shape
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import clip_ops
from tensorflow.python.ops import embedding_ops
from tensorflow.python.ops import init_ops
from tensorflow.python.ops import math_ops
from tensorflow.python.ops import nn_ops
from tensorflow.python.ops import variable_scope as vs

from tensorflow.python.ops.math_ops import sigmoid
from tensorflow.python.ops.math_ops import tanh

from tensorflow.python.platform import tf_logging as logging
from tensorflow.python.util import nest

import tensorflow as tf
import numpy as np


def _state_size_with_prefix(state_size, prefix=None):
  """Helper function that enables int or TensorShape shape specification.

  This function takes a size specification, which can be an integer or a
  TensorShape, and converts it into a list of integers. One may specify any
  additional dimensions that precede the final state size specification.

  Args:
    state_size: TensorShape or int that specifies the size of a tensor.
    prefix: optional additional list of dimensions to prepend.

  Returns:
    result_state_size: list of dimensions the resulting tensor size.
  """
  result_state_size = tensor_shape.as_shape(state_size).as_list()
  if prefix is not None:
    if not isinstance(prefix, list):
      raise TypeError("prefix of _state_size_with_prefix should be a list.")
    result_state_size = prefix + result_state_size
  return result_state_size


class RNNCell(object):
  """Abstract object representing an RNN cell.

  The definition of cell in this package differs from the definition used in the
  literature. In the literature, cell refers to an object with a single scalar
  output. The definition in this package refers to a horizontal array of such
  units.

  An RNN cell, in the most abstract setting, is anything that has
  a state and performs some operation that takes a matrix of inputs.
  This operation results in an output matrix with `self.output_size` columns.
  If `self.state_size` is an integer, this operation also results in a new
  state matrix with `self.state_size` columns.  If `self.state_size` is a
  tuple of integers, then it results in a tuple of `len(state_size)` state
  matrices, each with a column size corresponding to values in `state_size`.

  This module provides a number of basic commonly used RNN cells, such as
  LSTM (Long Short Term Memory) or GRU (Gated Recurrent Unit), and a number
  of operators that allow add dropouts, projections, or embeddings for inputs.
  Constructing multi-layer cells is supported by the class `MultiRNNCell`,
  or by calling the `rnn` ops several times. Every `RNNCell` must have the
  properties below and and implement `__call__` with the following signature.
  """

  def __call__(self, inputs, state, scope=None):
    """Run this RNN cell on inputs, starting from the given state.

    Args:
      inputs: `2-D` tensor with shape `[batch_size x input_size]`.
      state: if `self.state_size` is an integer, this should be a `2-D Tensor`
        with shape `[batch_size x self.state_size]`.  Otherwise, if
        `self.state_size` is a tuple of integers, this should be a tuple
        with shapes `[batch_size x s] for s in self.state_size`.
      scope: VariableScope for the created subgraph; defaults to class name.

    Returns:
      A pair containing:
      - Output: A `2-D` tensor with shape `[batch_size x self.output_size]`.
      - New state: Either a single `2-D` tensor, or a tuple of tensors matching
        the arity and shapes of `state`.
    """
    raise NotImplementedError("Abstract method")

  @property
  def state_size(self):
    """size(s) of state(s) used by this cell.

    It can be represented by an Integer, a TensorShape or a tuple of Integers
    or TensorShapes.
    """
    raise NotImplementedError("Abstract method")

  @property
  def output_size(self):
    """Integer or TensorShape: size of outputs produced by this cell."""
    raise NotImplementedError("Abstract method")

  def zero_state(self, batch_size, dtype):
    """Return zero-filled state tensor(s).

    Args:
      batch_size: int, float, or unit Tensor representing the batch size.
      dtype: the data type to use for the state.

    Returns:
      If `state_size` is an int or TensorShape, then the return value is a
      `N-D` tensor of shape `[batch_size x state_size]` filled with zeros.

      If `state_size` is a nested list or tuple, then the return value is
      a nested list or tuple (of the same structure) of `2-D` tensors with
    the shapes `[batch_size x s]` for each s in `state_size`.
    """
    state_size = self.state_size
    if nest.is_sequence(state_size):
      state_size_flat = nest.flatten(state_size)
      zeros_flat = [
          array_ops.zeros(
              array_ops.pack(_state_size_with_prefix(s, prefix=[batch_size])),
              dtype=dtype)
          for s in state_size_flat]
      for s, z in zip(state_size_flat, zeros_flat):
        z.set_shape(_state_size_with_prefix(s, prefix=[None]))
      zeros = nest.pack_sequence_as(structure=state_size,
                                    flat_sequence=zeros_flat)
    else:
      zeros_size = _state_size_with_prefix(state_size, prefix=[batch_size])
      zeros = array_ops.zeros(array_ops.pack(zeros_size), dtype=dtype)
      zeros.set_shape(_state_size_with_prefix(state_size, prefix=[None]))

    return zeros


class BasicRNNCell(RNNCell):
  """The most basic RNN cell."""

  def __init__(self, num_units, input_size=None, activation=tanh):
    if input_size is not None:
      logging.warn("%s: The input_size parameter is deprecated.", self)
    self._num_units = num_units
    self._activation = activation

  @property
  def state_size(self):
    return self._num_units

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Most basic RNN: output = new_state = activation(W * input + U * state + B)."""
    with vs.variable_scope(scope or type(self).__name__):  # "BasicRNNCell"
      output = self._activation(_linear([inputs, state], self._num_units, True))
    return output, output


class DeltaRNNCell(RNNCell):
  """The most basic RNN cell."""

  def __init__(self, num_units, input_size=None, activation=tanh):
    if input_size is not None:
      logging.warn("%s: The input_size parameter is deprecated.", self)
    self._num_units = num_units
    self._activation = activation

  @property
  def state_size(self):
    return self._num_units

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Most basic RNN: output = new_state = activation(W * input + U * state + B)."""
    with vs.variable_scope(scope or type(self).__name__):  # "BasicRNNCell"
      # state = self._activation(state)
      ot = _linear([inputs, state], self._num_units, True)
      # output = 0.1*tf.pow(ot,1/2) + state
      ot = self._activation(ot-state)*state
      output = ot + state
    return output, output


_DeltaRNNStateTuple = collections.namedtuple("DeltaRNStateTuple", ("prev_inputs", "h"))

class DeltaRNNStateTuple(_DeltaRNNStateTuple):
  """Tuple used by Field Cells for `state_size`, `zero_state`, and output state.
  Stores two elements: `(prev_inputs, h)`, in that order.
  Only used when `state_is_tuple=True`.
  """
  __slots__ = ()

  @property
  def dtype(self):
    (prev_inputs, h) = self
    if not prev_inputs.dtype == h.dtype:
      raise TypeError("Inconsistent internal state: %s vs %s" %
                      (str(prev_inputs.dtype), str(h.dtype)))
    return prev_inputs.dtype


class DeltaRNNCell2(RNNCell):
  """Basic Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, activation=tanh, state_is_tuple=True):
    """Initialize the basic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._input_size = input_size
    self._activation = activation
    self._state_is_tuple = state_is_tuple

  @property
  def state_size(self):
    return (DeltaRNNStateTuple(self._input_size, self._num_units)
            if self._state_is_tuple else self._input_size + self._num_units)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Field cell."""
    with vs.variable_scope(scope or "deltarnn_field_cell2") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._num_units])
      
      ot = _linear([prev_inputs, inputs, h], self._num_units, True)
      # output = 0.1*tf.pow(ot,1/2) + state
      ot = self._activation(ot)
      # output = ot + h
      output = ot

      new_inputs = inputs
      new_h = output

      if self._state_is_tuple:
        new_state = DeltaRNNStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return new_h, new_state


class GRUCell(RNNCell):
  """Gated Recurrent Unit cell (cf. http://arxiv.org/abs/1406.1078)."""

  def __init__(self, num_units, input_size=None, activation=tanh):
    if input_size is not None:
      logging.warn("%s: The input_size parameter is deprecated.", self)
    self._num_units = num_units
    self._activation = activation

  @property
  def state_size(self):
    return self._num_units

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Gated recurrent unit (GRU) with nunits cells."""
    with vs.variable_scope(scope or type(self).__name__):  # "GRUCell"
      with vs.variable_scope("Gates"):  # Reset gate and update gate.
        # We start with bias of 1.0 to not reset and not update.
        r, u = array_ops.split(1, 2, _linear([inputs, state],
                                             2 * self._num_units, True, 1.0))
        r, u = sigmoid(r), sigmoid(u)
      with vs.variable_scope("Candidate"):
        c = self._activation(_linear([inputs, r * state],
                                     self._num_units, True))
      new_h = u * state + (1 - u) * c
    return new_h, new_h


_LSTMStateTuple = collections.namedtuple("LSTMStateTuple", ("c", "h"))


class LSTMStateTuple(_LSTMStateTuple):
  """Tuple used by LSTM Cells for `state_size`, `zero_state`, and output state.

  Stores two elements: `(c, h)`, in that order.

  Only used when `state_is_tuple=True`.
  """
  __slots__ = ()

  @property
  def dtype(self):
    (c, h) = self
    if not c.dtype == h.dtype:
      raise TypeError("Inconsistent internal state: %s vs %s" %
                      (str(c.dtype), str(h.dtype)))
    return c.dtype


class BasicLSTMCell(RNNCell):
  """Basic LSTM recurrent network cell.

  The implementation is based on: http://arxiv.org/abs/1409.2329.

  We add forget_bias (default: 1) to the biases of the forget gate in order to
  reduce the scale of forgetting in the beginning of the training.

  It does not allow cell clipping, a projection layer, and does not
  use peep-hole connections: it is the basic baseline.

  For advanced models, please use the full LSTMCell that follows.
  """

  def __init__(self, num_units, forget_bias=1.0, input_size=None,
               state_is_tuple=True, activation=tanh):
    """Initialize the basic LSTM cell.

    Args:
      num_units: int, The number of units in the LSTM cell.
      forget_bias: float, The bias added to forget gates (see above).
      input_size: Deprecated and unused.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `c_state` and `m_state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
      activation: Activation function of the inner states.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    if input_size is not None:
      logging.warn("%s: The input_size parameter is deprecated.", self)
    self._num_units = num_units
    self._forget_bias = forget_bias
    self._state_is_tuple = state_is_tuple
    self._activation = activation

  @property
  def state_size(self):
    return (LSTMStateTuple(self._num_units, self._num_units)
            if self._state_is_tuple else 2 * self._num_units)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Long short-term memory cell (LSTM)."""
    with vs.variable_scope(scope or type(self).__name__):  # "BasicLSTMCell"
      # Parameters of gates are concatenated into one multiply for efficiency.
      if self._state_is_tuple:
        c, h = state
      else:
        c, h = array_ops.split(1, 2, state)
      concat = _linear([inputs, h], 4 * self._num_units, True)

      # i = input_gate, j = new_input, f = forget_gate, o = output_gate
      i, j, f, o = array_ops.split(1, 4, concat)

      new_c = (c * sigmoid(f + self._forget_bias) + sigmoid(i) *
               self._activation(j))
      new_h = self._activation(new_c) * sigmoid(o)

      if self._state_is_tuple:
        new_state = LSTMStateTuple(new_c, new_h)
      else:
        new_state = array_ops.concat(1, [new_c, new_h])
      return new_h, new_state


def _get_concat_variable(name, shape, dtype, num_shards):
  """Get a sharded variable concatenated into one tensor."""
  sharded_variable = _get_sharded_variable(name, shape, dtype, num_shards)
  if len(sharded_variable) == 1:
    return sharded_variable[0]

  concat_name = name + "/concat"
  concat_full_name = vs.get_variable_scope().name + "/" + concat_name + ":0"
  for value in ops.get_collection(ops.GraphKeys.CONCATENATED_VARIABLES):
    if value.name == concat_full_name:
      return value

  concat_variable = array_ops.concat(0, sharded_variable, name=concat_name)
  ops.add_to_collection(ops.GraphKeys.CONCATENATED_VARIABLES,
                        concat_variable)
  return concat_variable


def _get_sharded_variable(name, shape, dtype, num_shards):
  """Get a list of sharded variables with the given dtype."""
  if num_shards > shape[0]:
    raise ValueError("Too many shards: shape=%s, num_shards=%d" %
                     (shape, num_shards))
  unit_shard_size = int(math.floor(shape[0] / num_shards))
  remaining_rows = shape[0] - unit_shard_size * num_shards

  shards = []
  for i in range(num_shards):
    current_size = unit_shard_size
    if i < remaining_rows:
      current_size += 1
    shards.append(vs.get_variable(name + "_%d" % i, [current_size] + shape[1:],
                                  dtype=dtype))
  return shards


class LSTMCell(RNNCell):
  """Long short-term memory unit (LSTM) recurrent network cell.

  The default non-peephole implementation is based on:

    http://deeplearning.cs.cmu.edu/pdfs/Hochreiter97_lstm.pdf

  S. Hochreiter and J. Schmidhuber.
  "Long Short-Term Memory". Neural Computation, 9(8):1735-1780, 1997.

  The peephole implementation is based on:

    https://research.google.com/pubs/archive/43905.pdf

  Hasim Sak, Andrew Senior, and Francoise Beaufays.
  "Long short-term memory recurrent neural network architectures for
   large scale acoustic modeling." INTERSPEECH, 2014.

  The class uses optional peep-hole connections, optional cell clipping, and
  an optional projection layer.
  """

  def __init__(self, num_units, input_size=None,
               use_peepholes=False, cell_clip=None,
               initializer=None, num_proj=None, proj_clip=None,
               num_unit_shards=1, num_proj_shards=1,
               forget_bias=1.0, state_is_tuple=True,
               activation=tanh):
    """Initialize the parameters for an LSTM cell.

    Args:
      num_units: int, The number of units in the LSTM cell
      input_size: Deprecated and unused.
      use_peepholes: bool, set True to enable diagonal/peephole connections.
      cell_clip: (optional) A float value, if provided the cell state is clipped
        by this value prior to the cell output activation.
      initializer: (optional) The initializer to use for the weight and
        projection matrices.
      num_proj: (optional) int, The output dimensionality for the projection
        matrices.  If None, no projection is performed.
      proj_clip: (optional) A float value.  If `num_proj > 0` and `proj_clip` is
      provided, then the projected values are clipped elementwise to within
      `[-proj_clip, proj_clip]`.
      num_unit_shards: How to split the weight matrix.  If >1, the weight
        matrix is stored across num_unit_shards.
      num_proj_shards: How to split the projection matrix.  If >1, the
        projection matrix is stored across num_proj_shards.
      forget_bias: Biases of the forget gate are initialized by default to 1
        in order to reduce the scale of forgetting at the beginning of
        the training.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `c_state` and `m_state`.  If False, they are concatenated
        along the column axis.  This latter behavior will soon be deprecated.
      activation: Activation function of the inner states.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    if input_size is not None:
      logging.warn("%s: The input_size parameter is deprecated.", self)
    self._num_units = num_units
    self._use_peepholes = use_peepholes
    self._cell_clip = cell_clip
    self._initializer = initializer
    self._num_proj = num_proj
    self._proj_clip = proj_clip
    self._num_unit_shards = num_unit_shards
    self._num_proj_shards = num_proj_shards
    self._forget_bias = forget_bias
    self._state_is_tuple = state_is_tuple
    self._activation = activation

    if num_proj:
      self._state_size = (
          LSTMStateTuple(num_units, num_proj)
          if state_is_tuple else num_units + num_proj)
      self._output_size = num_proj
    else:
      self._state_size = (
          LSTMStateTuple(num_units, num_units)
          if state_is_tuple else 2 * num_units)
      self._output_size = num_units

  @property
  def state_size(self):
    return self._state_size

  @property
  def output_size(self):
    return self._output_size

  def __call__(self, inputs, state, scope=None):
    """Run one step of LSTM.

    Args:
      inputs: input Tensor, 2D, batch x num_units.
      state: if `state_is_tuple` is False, this must be a state Tensor,
        `2-D, batch x state_size`.  If `state_is_tuple` is True, this must be a
        tuple of state Tensors, both `2-D`, with column sizes `c_state` and
        `m_state`.
      scope: VariableScope for the created subgraph; defaults to "LSTMCell".

    Returns:
      A tuple containing:
      - A `2-D, [batch x output_dim]`, Tensor representing the output of the
        LSTM after reading `inputs` when previous state was `state`.
        Here output_dim is:
           num_proj if num_proj was set,
           num_units otherwise.
      - Tensor(s) representing the new state of LSTM after reading `inputs` when
        the previous state was `state`.  Same type and shape(s) as `state`.

    Raises:
      ValueError: If input size cannot be inferred from inputs via
        static shape inference.
    """
    num_proj = self._num_units if self._num_proj is None else self._num_proj

    if self._state_is_tuple:
      (c_prev, m_prev) = state
    else:
      c_prev = array_ops.slice(state, [0, 0], [-1, self._num_units])
      m_prev = array_ops.slice(state, [0, self._num_units], [-1, num_proj])

    dtype = inputs.dtype
    input_size = inputs.get_shape().with_rank(2)[1]
    if input_size.value is None:
      raise ValueError("Could not infer input size from inputs.get_shape()[-1]")
    with vs.variable_scope(scope or type(self).__name__,
                           initializer=self._initializer):  # "LSTMCell"
      concat_w = _get_concat_variable(
          "W", [input_size.value + num_proj, 4 * self._num_units],
          dtype, self._num_unit_shards)

      b = vs.get_variable(
          "B", shape=[4 * self._num_units],
          initializer=init_ops.zeros_initializer, dtype=dtype)

      # i = input_gate, j = new_input, f = forget_gate, o = output_gate
      cell_inputs = array_ops.concat(1, [inputs, m_prev])
      lstm_matrix = nn_ops.bias_add(math_ops.matmul(cell_inputs, concat_w), b)
      i, j, f, o = array_ops.split(1, 4, lstm_matrix)

      # Diagonal connections
      if self._use_peepholes:
        w_f_diag = vs.get_variable(
            "W_F_diag", shape=[self._num_units], dtype=dtype)
        w_i_diag = vs.get_variable(
            "W_I_diag", shape=[self._num_units], dtype=dtype)
        w_o_diag = vs.get_variable(
            "W_O_diag", shape=[self._num_units], dtype=dtype)

      if self._use_peepholes:
        c = (sigmoid(f + self._forget_bias + w_f_diag * c_prev) * c_prev +
             sigmoid(i + w_i_diag * c_prev) * self._activation(j))
      else:
        c = (sigmoid(f + self._forget_bias) * c_prev + sigmoid(i) *
             self._activation(j))

      if self._cell_clip is not None:
        # pylint: disable=invalid-unary-operand-type
        c = clip_ops.clip_by_value(c, -self._cell_clip, self._cell_clip)
        # pylint: enable=invalid-unary-operand-type

      if self._use_peepholes:
        m = sigmoid(o + w_o_diag * c) * self._activation(c)
      else:
        m = sigmoid(o) * self._activation(c)

      if self._num_proj is not None:
        concat_w_proj = _get_concat_variable(
            "W_P", [self._num_units, self._num_proj],
            dtype, self._num_proj_shards)

        m = math_ops.matmul(m, concat_w_proj)
        if self._proj_clip is not None:
          # pylint: disable=invalid-unary-operand-type
          m = clip_ops.clip_by_value(m, -self._proj_clip, self._proj_clip)
          # pylint: enable=invalid-unary-operand-type

    new_state = (LSTMStateTuple(c, m) if self._state_is_tuple
                 else array_ops.concat(1, [c, m]))
    return m, new_state


class OutputProjectionWrapper(RNNCell):
  """Operator adding an output projection to the given cell.

  Note: in many cases it may be more efficient to not use this wrapper,
  but instead concatenate the whole sequence of your outputs in time,
  do the projection on this batch-concatenated sequence, then split it
  if needed or directly feed into a softmax.
  """

  def __init__(self, cell, output_size):
    """Create a cell with output projection.

    Args:
      cell: an RNNCell, a projection to output_size is added to it.
      output_size: integer, the size of the output after projection.

    Raises:
      TypeError: if cell is not an RNNCell.
      ValueError: if output_size is not positive.
    """
    if not isinstance(cell, RNNCell):
      raise TypeError("The parameter cell is not RNNCell.")
    if output_size < 1:
      raise ValueError("Parameter output_size must be > 0: %d." % output_size)
    self._cell = cell
    self._output_size = output_size

  @property
  def state_size(self):
    return self._cell.state_size

  @property
  def output_size(self):
    return self._output_size

  def __call__(self, inputs, state, scope=None):
    """Run the cell and output projection on inputs, starting from state."""
    output, res_state = self._cell(inputs, state)
    # Default scope: "OutputProjectionWrapper"
    with vs.variable_scope(scope or type(self).__name__):
      projected = _linear(output, self._output_size, True)
    return projected, res_state


class InputProjectionWrapper(RNNCell):
  """Operator adding an input projection to the given cell.

  Note: in many cases it may be more efficient to not use this wrapper,
  but instead concatenate the whole sequence of your inputs in time,
  do the projection on this batch-concatenated sequence, then split it.
  """

  def __init__(self, cell, num_proj, input_size=None):
    """Create a cell with input projection.

    Args:
      cell: an RNNCell, a projection of inputs is added before it.
      num_proj: Python integer.  The dimension to project to.
      input_size: Deprecated and unused.

    Raises:
      TypeError: if cell is not an RNNCell.
    """
    if input_size is not None:
      logging.warn("%s: The input_size parameter is deprecated.", self)
    if not isinstance(cell, RNNCell):
      raise TypeError("The parameter cell is not RNNCell.")
    self._cell = cell
    self._num_proj = num_proj

  @property
  def state_size(self):
    return self._cell.state_size

  @property
  def output_size(self):
    return self._cell.output_size

  def __call__(self, inputs, state, scope=None):
    """Run the input projection and then the cell."""
    # Default scope: "InputProjectionWrapper"
    with vs.variable_scope(scope or type(self).__name__):
      projected = _linear(inputs, self._num_proj, True)
    return self._cell(projected, state)


class DropoutWrapper(RNNCell):
  """Operator adding dropout to inputs and outputs of the given cell."""

  def __init__(self, cell, input_keep_prob=1.0, output_keep_prob=1.0,
               seed=None):
    """Create a cell with added input and/or output dropout.

    Dropout is never used on the state.

    Args:
      cell: an RNNCell, a projection to output_size is added to it.
      input_keep_prob: unit Tensor or float between 0 and 1, input keep
        probability; if it is float and 1, no input dropout will be added.
      output_keep_prob: unit Tensor or float between 0 and 1, output keep
        probability; if it is float and 1, no output dropout will be added.
      seed: (optional) integer, the randomness seed.

    Raises:
      TypeError: if cell is not an RNNCell.
      ValueError: if keep_prob is not between 0 and 1.
    """
    if not isinstance(cell, RNNCell):
      raise TypeError("The parameter cell is not a RNNCell.")
    if (isinstance(input_keep_prob, float) and
        not (input_keep_prob >= 0.0 and input_keep_prob <= 1.0)):
      raise ValueError("Parameter input_keep_prob must be between 0 and 1: %d"
                       % input_keep_prob)
    if (isinstance(output_keep_prob, float) and
        not (output_keep_prob >= 0.0 and output_keep_prob <= 1.0)):
      raise ValueError("Parameter output_keep_prob must be between 0 and 1: %d"
                       % output_keep_prob)
    self._cell = cell
    self._input_keep_prob = input_keep_prob
    self._output_keep_prob = output_keep_prob
    self._seed = seed

  @property
  def state_size(self):
    return self._cell.state_size

  @property
  def output_size(self):
    return self._cell.output_size

  def __call__(self, inputs, state, scope=None):
    """Run the cell with the declared dropouts."""
    if (not isinstance(self._input_keep_prob, float) or
        self._input_keep_prob < 1):
      inputs = nn_ops.dropout(inputs, self._input_keep_prob, seed=self._seed)
    output, new_state = self._cell(inputs, state, scope)
    if (not isinstance(self._output_keep_prob, float) or
        self._output_keep_prob < 1):
      output = nn_ops.dropout(output, self._output_keep_prob, seed=self._seed)
    return output, new_state


class EmbeddingWrapper(RNNCell):
  """Operator adding input embedding to the given cell.

  Note: in many cases it may be more efficient to not use this wrapper,
  but instead concatenate the whole sequence of your inputs in time,
  do the embedding on this batch-concatenated sequence, then split it and
  feed into your RNN.
  """

  def __init__(self, cell, embedding_classes, embedding_size, initializer=None):
    """Create a cell with an added input embedding.

    Args:
      cell: an RNNCell, an embedding will be put before its inputs.
      embedding_classes: integer, how many symbols will be embedded.
      embedding_size: integer, the size of the vectors we embed into.
      initializer: an initializer to use when creating the embedding;
        if None, the initializer from variable scope or a default one is used.

    Raises:
      TypeError: if cell is not an RNNCell.
      ValueError: if embedding_classes is not positive.
    """
    if not isinstance(cell, RNNCell):
      raise TypeError("The parameter cell is not RNNCell.")
    if embedding_classes <= 0 or embedding_size <= 0:
      raise ValueError("Both embedding_classes and embedding_size must be > 0: "
                       "%d, %d." % (embedding_classes, embedding_size))
    self._cell = cell
    self._embedding_classes = embedding_classes
    self._embedding_size = embedding_size
    self._initializer = initializer

  @property
  def state_size(self):
    return self._cell.state_size

  @property
  def output_size(self):
    return self._cell.output_size

  def __call__(self, inputs, state, scope=None):
    """Run the cell on embedded inputs."""
    with vs.variable_scope(scope or type(self).__name__):  # "EmbeddingWrapper"
      with ops.device("/cpu:0"):
        if self._initializer:
          initializer = self._initializer
        elif vs.get_variable_scope().initializer:
          initializer = vs.get_variable_scope().initializer
        else:
          # Default initializer for embeddings should have variance=1.
          sqrt3 = math.sqrt(3)  # Uniform(-sqrt(3), sqrt(3)) has variance=1.
          initializer = init_ops.random_uniform_initializer(-sqrt3, sqrt3)

        if type(state) is tuple:
          data_type = state[0].dtype
        else:
          data_type = state.dtype

        embedding = vs.get_variable(
            "embedding", [self._embedding_classes, self._embedding_size],
            initializer=initializer,
            dtype=data_type)
        embedded = embedding_ops.embedding_lookup(
            embedding, array_ops.reshape(inputs, [-1]))
    return self._cell(embedded, state)


class MultiRNNCell(RNNCell):
  """RNN cell composed sequentially of multiple simple cells."""

  def __init__(self, cells, state_is_tuple=True):
    """Create a RNN cell composed sequentially of a number of RNNCells.

    Args:
      cells: list of RNNCells that will be composed in this order.
      state_is_tuple: If True, accepted and returned states are n-tuples, where
        `n = len(cells)`.  If False, the states are all
        concatenated along the column axis.  This latter behavior will soon be
        deprecated.

    Raises:
      ValueError: if cells is empty (not allowed), or at least one of the cells
        returns a state tuple but the flag `state_is_tuple` is `False`.
    """
    if not cells:
      raise ValueError("Must specify at least one cell for MultiRNNCell.")
    self._cells = cells
    self._state_is_tuple = state_is_tuple
    if not state_is_tuple:
      if any(nest.is_sequence(c.state_size) for c in self._cells):
        raise ValueError("Some cells return tuples of states, but the flag "
                         "state_is_tuple is not set.  State sizes are: %s"
                         % str([c.state_size for c in self._cells]))

  @property
  def state_size(self):
    if self._state_is_tuple:
      return tuple(cell.state_size for cell in self._cells)
    else:
      return sum([cell.state_size for cell in self._cells])

  @property
  def output_size(self):
    return self._cells[-1].output_size

  def __call__(self, inputs, state, scope=None):
    """Run this multi-layer cell on inputs, starting from state."""
    with vs.variable_scope(scope or type(self).__name__):  # "MultiRNNCell"
      cur_state_pos = 0
      cur_inp = inputs
      new_states = []
      for i, cell in enumerate(self._cells):
        with vs.variable_scope("Cell%d" % i):
          if self._state_is_tuple:
            if not nest.is_sequence(state):
              raise ValueError(
                  "Expected state to be a tuple of length %d, but received: %s"
                  % (len(self.state_size), state))
            cur_state = state[i]
          else:
            cur_state = array_ops.slice(
                state, [0, cur_state_pos], [-1, cell.state_size])
            cur_state_pos += cell.state_size
          cur_inp, new_state = cell(cur_inp, cur_state)
          new_states.append(new_state)
    new_states = (tuple(new_states) if self._state_is_tuple
                  else array_ops.concat(1, new_states))
    return cur_inp, new_states


class _SlimRNNCell(RNNCell):
  """A simple wrapper for slim.rnn_cells."""

  def __init__(self, cell_fn):
    """Create a SlimRNNCell from a cell_fn.

    Args:
      cell_fn: a function which takes (inputs, state, scope) and produces the
        outputs and the new_state. Additionally when called with inputs=None and
        state=None it should return (initial_outputs, initial_state).

    Raises:
      TypeError: if cell_fn is not callable
      ValueError: if cell_fn cannot produce a valid initial state.
    """
    if not callable(cell_fn):
      raise TypeError("cell_fn %s needs to be callable", cell_fn)
    self._cell_fn = cell_fn
    self._cell_name = cell_fn.func.__name__
    init_output, init_state = self._cell_fn(None, None)
    output_shape = init_output.get_shape()
    state_shape = init_state.get_shape()
    self._output_size = output_shape.with_rank(2)[1].value
    self._state_size = state_shape.with_rank(2)[1].value
    if self._output_size is None:
      raise ValueError("Initial output created by %s has invalid shape %s" %
                       (self._cell_name, output_shape))
    if self._state_size is None:
      raise ValueError("Initial state created by %s has invalid shape %s" %
                       (self._cell_name, state_shape))

  @property
  def state_size(self):
    return self._state_size

  @property
  def output_size(self):
    return self._output_size

  def __call__(self, inputs, state, scope=None):
    scope = scope or self._cell_name
    output, state = self._cell_fn(inputs, state, scope=scope)
    return output, state


def _linear(args, output_size, bias, bias_start=0.0, scope=None):
  """Linear map: sum_i(args[i] * W[i]), where W[i] is a variable.

  Args:
    args: a 2D Tensor or a list of 2D, batch x n, Tensors.
    output_size: int, second dimension of W[i].
    bias: boolean, whether to add a bias term or not.
    bias_start: starting value to initialize the bias; 0 by default.
    scope: VariableScope for the created subgraph; defaults to "Linear".

  Returns:
    A 2D Tensor with shape [batch x output_size] equal to
    sum_i(args[i] * W[i]), where W[i]s are newly created matrices.

  Raises:
    ValueError: if some of the arguments has unspecified or wrong shape.
  """
  if args is None or (nest.is_sequence(args) and not args):
    raise ValueError("`args` must be specified")
  if not nest.is_sequence(args):
    args = [args]

  # Calculate the total size of arguments on dimension 1.
  total_arg_size = 0
  shapes = [a.get_shape().as_list() for a in args]
  for shape in shapes:
    if len(shape) != 2:
      raise ValueError("Linear is expecting 2D arguments: %s" % str(shapes))
    if not shape[1]:
      raise ValueError("Linear expects shape[1] of arguments: %s" % str(shapes))
    else:
      total_arg_size += shape[1]

  dtype = [a.dtype for a in args][0]

  # Now the computation.
  with vs.variable_scope(scope or "Linear"):
    matrix = vs.get_variable(
        "Matrix", [total_arg_size, output_size], dtype=dtype)
    if len(args) == 1:
      res = math_ops.matmul(args[0], matrix)
    else:
      res = math_ops.matmul(array_ops.concat(1, args), matrix)
    if not bias:
      return res
    bias_term = vs.get_variable(
        "Bias", [output_size],
        dtype=dtype,
        initializer=init_ops.constant_initializer(
            bias_start, dtype=dtype))
  return res + bias_term


def _linear2(args, output_size, bias, bias_start=0.0, scope=None):
  """Linear map: sum_i(args[i] * W[i]), where W[i] is a variable.

  Args:
    args: a 2D Tensor or a list of 2D, batch x n, Tensors.
    output_size: int, second dimension of W[i].
    bias: boolean, whether to add a bias term or not.
    bias_start: starting value to initialize the bias; 0 by default.
    scope: VariableScope for the created subgraph; defaults to "Linear".

  Returns:
    A 2D Tensor with shape [batch x output_size] equal to
    sum_i(args[i] * W[i]), where W[i]s are newly created matrices.

  Raises:
    ValueError: if some of the arguments has unspecified or wrong shape.
  """
  if args is None or (nest.is_sequence(args) and not args):
    raise ValueError("`args` must be specified")
  if not nest.is_sequence(args):
    args = [args]

  # Calculate the total size of arguments on dimension 1.
  shapes = [a.get_shape().as_list() for a in args]
  total_arg_size = shapes[0][1]
  for shape in shapes:
    if len(shape) != 2:
      raise ValueError("Linear is expecting 2D arguments: %s" % str(shapes))
    if not shape[1]:
      raise ValueError("Linear expects shape[1] of arguments: %s" % str(shapes))
    if not shape[1] == total_arg_size:
      raise ValueError("Linear expects shape[1] to be same for all arguments: %s" % str(shapes))

  dtype = [a.dtype for a in args][0]

  # Now the computation.
  with vs.variable_scope(scope or "Linear"):
    matrix = vs.get_variable(
        "Matrix", [total_arg_size, output_size], dtype=dtype)
    if bias:
      bias_term = vs.get_variable(
          "Bias", [output_size],
          dtype=dtype,
          initializer=init_ops.constant_initializer(
              bias_start, dtype=dtype))

    res = []
    for a in args:
      res_a = math_ops.matmul(a, matrix)
      if bias:
        res_a += bias_term
      res += [res_a]

  return res


class DNNField(object):

  def __init__(self, input_size, num_units, hidden_units=[], activation=tanh):
    self._input_size = input_size
    self._num_units = num_units
    self._hidden_units = hidden_units
    # self._units = [input_size] + hidden_units + [input_size]
    self._activation = activation

  def dnn_fieldA(self,inputs):
    units = [self._input_size] + self._hidden_units + [self._input_size]

    fields = []
    for f in range(self._num_units):
      with tf.variable_scope('field_'+str(f)):
        prev = inputs
        for i, unit in enumerate(units[:-1]):
          with tf.variable_scope('layer_'+str(i)) as scope:
            # Wi = tf.Variable(tf.random_normal([unit,units[i+1]]))
            # bi = tf.Variable(tf.zeros([units[i+1]]))
            # # if i == len(self._units) - 2:
            # #   hiddeni = tf.matmul(prev,Wi)+bi
            # # else:
            # hiddeni = self._activation(tf.matmul(prev,Wi)+bi)
            hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
            prev = hiddeni
      fields += [hiddeni]
    return tf.pack(fields)

  def dnn_field2A(self,inputs):
    # hidden = [input_size,5<input_size]
    units = [self._input_size] + self._hidden_units + [self._num_units*self._input_size]

    prev = inputs
    for i, unit in enumerate(units[:-1]):
      with tf.variable_scope('layer_'+str(i)) as scope:
        hiddeni = _linear(args=prev,output_size=units[i+1],bias=True)
        if i < len(units) - 2:
          hiddeni = self._activation(hiddeni)
        prev = hiddeni

    fields = tf.reshape(hiddeni,shape=[-1,self._num_units,self._input_size])
    fields = tf.transpose(fields,[1,0,2])

    return fields

  def dnn_field2AB(self,inputs):
    units = [self._input_size] + self._hidden_units + [self._num_units*self._input_size]

    prev = inputs
    for i, unit in enumerate(units[:-1]):
      with tf.variable_scope('layer_'+str(i)) as scope:
        hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
        prev = hiddeni

    fields = tf.reshape(hiddeni,shape=[-1,self._num_units,self._input_size])
    fields = tf.transpose(fields,[1,0,2])

    return fields

  def dnn_field3A(self,inputs):
    inputs = tf.expand_dims(inputs,dim=1)  # [None,_input_size] --> [None,1,_input_size]
    dtype = inputs.dtype

    units = [self._input_size] + self._hidden_units + [self._input_size]

    with vs.variable_scope('broadcast_field'):
      matrix = vs.get_variable(
          "Matrix", [self._num_units, self._input_size], dtype=dtype)
      bias_term = vs.get_variable(
          "Bias", [self._input_size],
          dtype=dtype,
          initializer=init_ops.constant_initializer(
              0., dtype=dtype))

      prev = tf.multiply(inputs,matrix) + bias_term
      prev = tf.unpack(prev)

    for i, unit in enumerate(units[:-1]):
      with tf.variable_scope('layer_'+str(i)) as scope:
        if i == len(units) - 2:
          hiddeni = self._activation(_linear2(args=prev,output_size=units[i+1],bias=True))
        else:
          hiddeni = _linear2(args=prev,output_size=units[i+1],bias=True)
        prev = hiddeni

    # fields = tf.reshape(hiddeni,shape=[-1,self._num_units,self._input_size])
    fields = tf.pack(hiddeni)
    fields = tf.transpose(fields,[1,0,2])

    return fields

  def dnn_kernel_int(self,x,dx):  # asymmetric kernel
    units = [2*self._input_size] + self._hidden_units + [self._num_units]

    prev = [x,dx]
    for i, unit in enumerate(units[:-1]):
      with tf.variable_scope('layer_'+str(i)) as scope:
        if i == len(units) - 2:
          hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
        # else:
        #   hiddeni = _linear(args=prev,output_size=units[i+1],bias=True)
        prev = hiddeni

    path_int = hiddeni

    return path_int

  def dnn_kernel_int2(self,x,dx):  # asymmetric kernel
    units = [self._input_size] + self._hidden_units + [self._num_units]

    prev = x
    with tf.variable_scope('field') as scope:
      for i, unit in enumerate(units[:-1]):
        with tf.variable_scope('layer_'+str(i)) as scope:
          if i == len(units) - 2:
            hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
          # else:
          #   hiddeni = _linear(args=prev,output_size=units[i+1],bias=True)
          prev = hiddeni
    field = hiddeni

    prev = dx
    with tf.variable_scope('phi_dx') as scope:
      for i, unit in enumerate(units[:-1]):
        with tf.variable_scope('layer_'+str(i)) as scope:
          if i == len(units) - 2:
            hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
          # else:
          #   hiddeni = _linear(args=prev,output_size=units[i+1],bias=True)
          prev = hiddeni
    phi_dx = hiddeni


    path_int = field*phi_dx

    return path_int

  def dnn_dynfield(self,inputs,h):
    # h = tanh(h)
    units = [self._input_size+self._num_units] + self._hidden_units + [self._num_units*self._input_size]

    # # prev = array_ops.concat(1, [inputs, h])
    # prev = inputs
    # for i, unit in enumerate(units[:-1]):
    #   with tf.variable_scope('vec_layer_'+str(i)) as scope:
    #     # if i == len(units) - 2:
    #     #   hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
    #     # else:
    #     #   hiddeni = _linear(args=prev,output_size=units[i+1],bias=True)
    #     hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
    #     prev = hiddeni
    # vectors = hiddeni

    prev = [inputs, h]
    for i, unit in enumerate(units[:-1]):
      with tf.variable_scope('amp_layer_'+str(i)) as scope:
        if i == len(units) - 2:
          hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
        else:
          hiddeni = _linear(args=prev,output_size=units[i+1],bias=True)
          # hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
        prev = hiddeni
    amplitude = hiddeni

    # fields = amplitude*vectors
    fields = amplitude

    fields = tf.reshape(fields,shape=[-1,self._num_units,self._input_size])
    fields = tf.transpose(fields,[1,0,2])

    return fields

_FieldStateTuple = collections.namedtuple("FieldStateTuple", ("prev_inputs", "h"))

class FieldStateTuple(_FieldStateTuple):
  """Tuple used by Field Cells for `state_size`, `zero_state`, and output state.
  Stores two elements: `(prev_inputs, h)`, in that order.
  Only used when `state_is_tuple=True`.
  """
  __slots__ = ()

  @property
  def dtype(self):
    (prev_inputs, h) = self
    if not prev_inputs.dtype == h.dtype:
      raise TypeError("Inconsistent internal state: %s vs %s" %
                      (str(prev_inputs.dtype), str(h.dtype)))
    return prev_inputs.dtype


class BasicFieldCell(RNNCell):
  """Basic Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, n_inter=0, keep_prob=1.,
               state_is_tuple=True):
    """Initialize the basic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._num_units)
            if self._state_is_tuple else self._input_size + self._num_units)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Field cell."""
    with vs.variable_scope(scope or "basic_field_cell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._num_units])
      
      # print('higher scope name')
      # print(scope.name)
      
      # print('prev_field')
      # prev_fields = self._fields(prev_inputs)

      # scope.reuse_variables()
      # print('field')
      # fields = self._fields(inputs)

      # trapezoid_fields = 0.5 * (prev_fields + fields)

      # for n in range(1,self._n_inter+1):
      #   alpha = n/(self._n_inter+1)
      #   inter = (1-alpha)*prev_inputs + alpha*inputs
      #   print('int_field '+str(n))
      #   trapezoid_fields += self._fields(inter)
      
      # d_inputs = (inputs - prev_inputs)/(self._n_inter+1)

      w = 1.0*0.5*np.cos(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
      w = w/np.sum(w)

      trapezoid_fields = w[0]*self._fields(prev_inputs)
      scope.reuse_variables()

      for n in range(1,self._n_inter+2):
        alpha = n/(self._n_inter+1)
        inter = (1-alpha)*prev_inputs + alpha*inputs
        trapezoid_fields += w[n]*self._fields(inter)

      d_inputs = (inputs - prev_inputs)

      path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
      path_int = tf.transpose(path_int)

      mask = tf.nn.dropout(self._mask,keep_prob=self._keep_prob)*self._keep_prob  # dropout automatically scales by 1/keep_prob (unwanted)

      new_h = mask*path_int + h
      new_inputs = mask*inputs + (1-mask)*prev_inputs

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return new_h, new_state


class BasicFieldCell2(RNNCell):
  """Basic Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the basic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Field cell."""
    with vs.variable_scope(scope or "basic_field_cell2") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      w = 1.0*0.5*np.cos(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
      w = w/np.sum(w)

      trapezoid_fields = w[0]*self._fields(prev_inputs)
      scope.reuse_variables()

      for n in range(1,self._n_inter+2):
        alpha = n/(self._n_inter+1)
        inter = (1-alpha)*prev_inputs + alpha*inputs
        trapezoid_fields += w[n]*self._fields(inter)

      d_inputs = (inputs - prev_inputs)

      path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
      path_int = tf.transpose(path_int)

      mask = tf.nn.dropout(self._mask,keep_prob=self._keep_prob)*self._keep_prob  # dropout automatically scales by 1/keep_prob (unwanted)

      new_h = mask*path_int + h
      new_inputs = mask*inputs + (1-mask)*prev_inputs

    with vs.variable_scope('output_activation',reuse=None):
      output = _linear(args=new_h,output_size=self._num_units,bias=True)
      if self._activation is not None:
        output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class DynamicFieldCell(RNNCell):
  """Dynamic Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, n_inter=0, keep_prob=1.,
               state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._num_units)
            if self._state_is_tuple else self._input_size + self._num_units)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Dynamic Field cell."""
    with vs.variable_scope(scope or "dynamic_field_cell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._num_units])

      w = 1.0*0.5*np.cos(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
      w = w/np.sum(w)

      trapezoid_fields = w[0]*self._fields(prev_inputs,h)
      scope.reuse_variables()

      for n in range(1,self._n_inter+2):
        alpha = n/(self._n_inter+1)
        inter = (1-alpha)*prev_inputs + alpha*inputs
        trapezoid_fields += w[n]*self._fields(inter,h)

      d_inputs = (inputs - prev_inputs)

      path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
      path_int = tf.transpose(path_int)

      mask = tf.nn.dropout(self._mask,keep_prob=self._keep_prob)*self._keep_prob  # dropout automatically scales by 1/keep_prob (unwanted)

      new_h = mask*path_int + h
      new_inputs = mask*inputs + (1-mask)*prev_inputs

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return new_h, new_state


class DynamicFieldCell2(RNNCell):
  """Dynamic Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Dynamic Field cell."""
    with vs.variable_scope(scope or "dynamic_field_cell2") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # h_tanh = tanh(h)
      h_tanh = h

      w = 1.0*0.5*np.cos(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
      w = w/np.sum(w)

      trapezoid_fields = w[0]*self._fields(prev_inputs,h_tanh)
      scope.reuse_variables()

      for n in range(1,self._n_inter+2):
        alpha = n/(self._n_inter+1)
        inter = (1-alpha)*prev_inputs + alpha*inputs
        trapezoid_fields += w[n]*self._fields(inter,h_tanh)

      d_inputs = (inputs - prev_inputs)

      path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
      path_int = tf.transpose(path_int)

      mask = tf.nn.dropout(self._mask,keep_prob=self._keep_prob)*self._keep_prob  # dropout automatically scales by 1/keep_prob (unwanted)

      new_h = mask*path_int + h
      new_inputs = mask*inputs + (1-mask)*prev_inputs

    with vs.variable_scope('output_activation',reuse=None):
      output = _linear(args=new_h,output_size=self._num_units,bias=True)
      if self._activation is not None:
        output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMFieldCell(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_cell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          temp = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        with vs.variable_scope("layer_1") as scope:
          hk = _linear(args=temp,output_size=self._hidden_size,bias=True)

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        trapezoid_fields = w[0]*self._fields(prev_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          trapezoid_fields += w[n]*self._fields(inter)
        d_inputs = (inputs - prev_inputs)
        path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
        path_int = tf.transpose(path_int)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(_linear(args=[inputs,h],output_size=self._hidden_size,bias=True))

      new_h = weights*hk+(1-weights)*hk_
      new_inputs = inputs
      # output = new_h
      with vs.variable_scope('output_activation',reuse=None):
        output = _linear(args=new_h,output_size=self._num_units,bias=True)
        if self._activation is not None:
          output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMFieldCell2(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_cell2") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          hk = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        # with vs.variable_scope("layer_1") as scope:
        #   hk = self._activation(_linear(args=hk,output_size=self._hidden_size,bias=True))

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        trapezoid_fields = w[0]*self._fields(prev_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          trapezoid_fields += w[n]*self._fields(inter)
        d_inputs = (inputs - prev_inputs)
        path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
        path_int = tf.transpose(path_int)
        # inv_h = 0.5*tf.log((1+h)/(1-h))
        # hk_ = self._activation(path_int + inv_h)
        hk_ = h + path_int

      # prediction weights
      with vs.variable_scope("vel") as scope:
        vel = _linear(args=[prev_inputs,inputs],output_size=self._hidden_size,bias=True)
      with vs.variable_scope("nonvel") as scope:
        nonvel = _linear(args=[hk,hk_],output_size=self._hidden_size,bias=True)
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(vel*nonvel)

      new_h = weights*hk+(1-weights)*hk_
      new_inputs = inputs
      # output = new_h
      with vs.variable_scope('output_activation',reuse=None):
        output = _linear(args=new_h,output_size=self._num_units,bias=True)
        if self._activation is not None:
          output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMFieldCell3(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_cell3") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          hk = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        # with vs.variable_scope("layer_1") as scope:
        #   hk = self._activation(_linear(args=hk,output_size=self._hidden_size,bias=True))

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        trapezoid_fields = w[0]*self._fields(prev_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          trapezoid_fields += w[n]*self._fields(inter)
        d_inputs = (inputs - prev_inputs)
        path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
        path_int = tf.transpose(path_int)
        # inv_h = 0.5*tf.log((1+h)/(1-h))
        # hk_ = self._activation(path_int + inv_h)
        hk_ = h + path_int

      # prediction weights
      with vs.variable_scope("vel") as scope:
        vel = _linear(args=[prev_inputs,inputs],output_size=self._hidden_size,bias=True)
      with vs.variable_scope("nonvel") as scope:
        nonvel = _linear(args=[hk,hk_],output_size=self._hidden_size,bias=True)
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(vel*nonvel)

      new_h = (1-weights)*hk+weights*hk_
      new_inputs = inputs
      output = new_h
      # with vs.variable_scope('output_activation',reuse=None):
      #   output = _linear(args=new_h,output_size=self._num_units,bias=True)
      #   if self._activation is not None:
      #     output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMFieldCell4(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_cell4") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          temp = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        with vs.variable_scope("layer_1") as scope:
          hk = _linear(args=temp,output_size=self._hidden_size,bias=True)

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        trapezoid_fields = w[0]*self._fields(prev_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          trapezoid_fields += w[n]*self._fields(inter)
        d_inputs = (inputs - prev_inputs)
        path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
        path_int = tf.transpose(path_int)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(_linear(args=[inputs,path_int],output_size=self._hidden_size,bias=True))

      new_h = weights*hk+(1-weights)*hk_
      new_inputs = inputs
      # output = new_h
      with vs.variable_scope('output_activation',reuse=None):
        output = _linear(args=new_h,output_size=self._num_units,bias=True)
        if self._activation is not None:
          output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMFieldCell5(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_cell4") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          hk = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        with vs.variable_scope("layer_1") as scope:
          hk = _linear(args=hk,output_size=self._hidden_size,bias=True)

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        trapezoid_fields = w[0]*self._fields(prev_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          trapezoid_fields += w[n]*self._fields(inter)
        d_inputs = (inputs - prev_inputs)
        path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
        path_int = tf.transpose(path_int)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(_linear(args=[inputs,path_int],output_size=self._hidden_size,bias=True))

      new_h = weights*hk+(1-weights)*hk_
      new_inputs = inputs
      output = self._activation(new_h)
      # with vs.variable_scope('output_activation',reuse=None):
      #   output = _linear(args=new_h,output_size=self._num_units,bias=True)
      #   if self._activation is not None:
      #     output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMKernelCell(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0,
               activation=tanh, state_is_tuple=True, keep_prob=1.):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._activation = activation
    self._mask = tf.ones(hidden_size)
    self._keep_prob = keep_prob

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_kernelcell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          hk = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        # with vs.variable_scope("layer_1") as scope:
        #   hk = _linear(args=hk,output_size=self._hidden_size,bias=True)

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        d_inputs = (inputs - prev_inputs)
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        path_int = w[0]*self._fields(prev_inputs,d_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          path_int += w[n]*self._fields(inter,d_inputs)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        Sprime = _linear(args=[d_inputs,path_int],output_size=self._hidden_size,bias=True)
        # weights = tf.exp(-Sprime**2.)
        weights = sigmoid(Sprime)

      mask = tf.nn.dropout(self._mask,keep_prob=self._keep_prob)*self._keep_prob
      weights = weights*mask

      output_h = (1-weights)*hk+weights*hk_

      new_h = (1-mask)*h + mask*output_h
      new_inputs = (1-mask)*prev_inputs + mask*inputs
      # new_inputs = prev_inputs

      output = output_h


      # with vs.variable_scope('output_activation',reuse=None):
      #   output = _linear(args=new_h,output_size=self._num_units,bias=True)
      #   if self._activation is not None:
      #     output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


_PathFieldStateTuple = collections.namedtuple("PathFieldStateTuple", ("prev_inputs", "h", "prev_mask"))


class LSTMKernelPathCell(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0,
               activation=tanh, state_is_tuple=True, keep_prob=1.,N_path=1):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._activation = activation
    self._keep_prob = keep_prob

  @property
  def state_size(self):
    return (_PathFieldStateTuple(self._input_size, self._hidden_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + 2*self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_kernelcell") as scope:
      if self._state_is_tuple:
        prev_inputs, h, prev_mask = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])
        prev_mask = array_ops.slice(state, [0, self._input_size + self._hidden_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          hk = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        # with vs.variable_scope("layer_1") as scope:
        #   hk = _linear(args=hk,output_size=self._hidden_size,bias=True)

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # w = 1.0*0.5*np.constructing(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        d_inputs = (inputs - prev_inputs)
        w = np.ones(self._n_inter+2)
        w = w/np.sum(w)
        path_int = w[0]*self._fields(prev_inputs,d_inputs)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          path_int += w[n]*self._fields(inter,d_inputs)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        Sprime = _linear(args=[d_inputs,path_int],output_size=self._hidden_size,bias=True)
        # weights = tf.exp(-Sprime**2.)
        weights = sigmoid(Sprime)

      # draw random variable and once it says stay, pass it as an extra hidden state, and stick to the normal path rest of the way
      mask = tf.nn.dropout(tf.ones_like(inputs),keep_prob=self._keep_prob)*self._keep_prob
      # mask2 = tf.nn.dropout(self._mask,keep_prob=.5)*.5
      # mask = tf.clip_by_value(mask+mask2*prev_mask,0,1)
      weights = weights*mask

      output_h = (1-weights)*hk+weights*hk_

      new_h = (1-mask)*h + mask*output_h
      new_inputs = (1-mask)*prev_inputs + mask*inputs

      # print(prev_mask.get_shape())
      # print(mask.get_shape())
      # new_mask = prev_mask
      new_mask = mask
      # new_inputs = prev_inputs

      output = output_h


      # with vs.variable_scope('output_activation',reuse=None):
      #   output = _linear(args=new_h,output_size=self._num_units,bias=True)
      #   if self._activation is not None:
      #     output = self._activation(output)

      if self._state_is_tuple:
        new_state = _PathFieldStateTuple(new_inputs, new_h, new_mask)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h, new_mask])
      
      return output, new_state


class LSTMFieldDynCell(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields = fields
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_dyncell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          temp = self._activation(_linear(args=inputs,output_size=self._hidden_size,bias=True))
        with vs.variable_scope("layer_1") as scope:
          hk = _linear(args=temp,output_size=self._hidden_size,bias=True)

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        w = 1.0*0.5*np.cos(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
        w = w/np.sum(w)
        trapezoid_fields = w[0]*self._fields(prev_inputs,0*h)
        scope.reuse_variables()
        for n in range(1,self._n_inter+2):
          alpha = n/(self._n_inter+1)
          inter = (1-alpha)*prev_inputs + alpha*inputs
          trapezoid_fields += w[n]*self._fields(inter,0*h)
        d_inputs = (inputs - prev_inputs)
        path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
        path_int = tf.transpose(path_int)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(_linear(args=[inputs,h],output_size=self._hidden_size,bias=True))

      new_h = weights*hk+(1-weights)*hk_
      new_inputs = inputs
      # output = new_h
      with vs.variable_scope('output_activation',reuse=None):
        output = _linear(args=new_h,output_size=self._num_units,bias=True)
        if self._activation is not None:
          output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class LSTMFieldKernelCell(RNNCell):
  """LSTM Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, hidden_size, n_inter=0, keep_prob=1.,
               activation=tanh, state_is_tuple=True):
    """Initialize the dynamic Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._hidden_size = hidden_size
    self._input_size = input_size
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple
    self._mask = tf.ones(1)
    self._keep_prob = keep_prob
    self._activation = activation

  @property
  def state_size(self):
    return (FieldStateTuple(self._input_size, self._hidden_size)
            if self._state_is_tuple else self._input_size + self._hidden_size)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """LSTM Field cell."""
    with vs.variable_scope(scope or "lstm_field_kernelcell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._hidden_size])

      # markov prediction
      with vs.variable_scope("markov_pred") as scope:
        with vs.variable_scope("layer_0") as scope:
          temp = _linear(args=inputs,output_size=self._hidden_size,bias=True)
          temp = self._activation(temp)
        # with vs.variable_scope("layer_1") as scope:
          # hk = _linear(args=temp,output_size=self._hidden_size,bias=True)
          hk = temp

      # sequence prediction
      with vs.variable_scope("seq_pred") as scope:
        # with vs.variable_scope("amp") as scope:
        #   amp = sigmoid(_linear(args=[prev_inputs,inputs],output_size=self._hidden_size,bias=True))
        # with vs.variable_scope("vec") as scope:
        #   vec = self._activation(_linear(args=[prev_inputs,inputs],output_size=self._hidden_size,bias=True))
        with vs.variable_scope("layer_0") as scope:
          temp = self._activation(_linear(args=[prev_inputs,inputs],output_size=self._hidden_size,bias=True))
        # with vs.variable_scope("layer_1") as scope:
          # path_int = _linear(args=temp,output_size=self._hidden_size,bias=True)
          path_int = temp
          # path_int = amp*vec
        # hk_ = self._activation(path_int + h)
        hk_ = path_int + h

      # prediction weights
      with vs.variable_scope("weights") as scope:
        weights = sigmoid(_linear(args=[inputs,h],output_size=self._hidden_size,bias=True))

      # new_h = weights*hk+(1-weights)*hk_
      output = weights*hk+(1-weights)*hk_
      new_h = tanh(output)
      # new_h = output

      new_inputs = inputs

      # output = new_h
      # with vs.variable_scope('output_activation',reuse=None):
      #   output = _linear(args=new_h,output_size=self._num_units,bias=True)
      #   if self._activation is not None:
      #     output = self._activation(output)

      if self._state_is_tuple:
        new_state = FieldStateTuple(new_inputs, new_h)
      else:
        new_state = array_ops.concat(1, [new_inputs, new_h])
      
      return output, new_state


class DNNKernelField(object):

  def __init__(self, input_size, num_units, hidden_units=[], activation=tanh):
    self._input_size = input_size
    self._num_units = num_units
    self._hidden_units = hidden_units
    self._activation = activation

  def dnn_ker_field(self,inputs_0,inputs_f):
    inputs = array_ops.concat(1, [inputs_0, inputs_f])

    units = [2*self._input_size] + self._hidden_units + [self._num_units]

    prev = inputs
    for i, unit in enumerate(units[:-1]):
      with tf.variable_scope('layer_'+str(i)) as scope:
        # Wi = tf.Variable(tf.random_normal([unit,units[i+1]]))
        # bi = tf.Variable(tf.zeros([units[i+1]]))
        # # if i == len(self._units) - 2:
        # #   hiddeni = tf.matmul(prev,Wi)+bi
        # # else:
        # hiddeni = self._activation(tf.matmul(prev,Wi)+bi)
        hiddeni = self._activation(_linear(args=prev,output_size=units[i+1],bias=True))
        prev = hiddeni

    fields_kernel = hiddeni

    return fields_kernel

_KernelFieldStateTuple = collections.namedtuple("KernelFieldStateTuple", ("prev_inputs", "h"))

class KernelFieldStateTuple(_KernelFieldStateTuple):
  """Tuple used by Kernel Field Cells for `state_size`, `zero_state`, and output state.
  Stores two elements: `(prev_inputs, h)`, in that order.
  Only used when `state_is_tuple=True`.
  """
  __slots__ = ()

  @property
  def dtype(self):
    (prev_inputs, h) = self
    if not prev_inputs.dtype == h.dtype:
      raise TypeError("Inconsistent internal state: %s vs %s" %
                      (str(prev_inputs.dtype), str(h.dtype)))
    return prev_inputs.dtype


class KernelFieldCell(RNNCell):
  """Kernel Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields_kernel,
               state_is_tuple=True):
    """Initialize the Kernel Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields_kernel: FK(prev_input,input), function to compute fields kernel.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._num_units = num_units
    self._fields_kernel = fields_kernel
    self._input_size = input_size
    self._state_is_tuple = state_is_tuple

  @property
  def state_size(self):
    return (KernelFieldStateTuple(self._input_size, self._num_units)
            if self._state_is_tuple else self._input_size + self._num_units)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Kernel Field cell."""
    with vs.variable_scope(scope or "kernel_field_cell") as scope:
      if self._state_is_tuple:
        prev_inputs, h = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._num_units])

      
      path_int = self._fields_kernel(prev_inputs,inputs)
      new_h = path_int + h

      if self._state_is_tuple:
        new_state = FieldStateTuple(inputs, new_h)
      else:
        new_state = array_ops.concat(1, [inputs, new_h])
      
      return new_h, new_state


_QuantumFieldStateTuple = collections.namedtuple("QuantumFieldStateTuple", ("prev_inputs", "h", "q_inputs", "gamk"))

class QuantumFieldStateTuple(_QuantumFieldStateTuple):
  """Tuple used by Field Cells for `state_size`, `zero_state`, and output state.
  Stores four elements: `(prev_inputs, h, q_inputs, gamk)`, in that order.
  Only used when `state_is_tuple=True`.
  """
  __slots__ = ()

  @property
  def dtype(self):
    (prev_inputs, h, q_inputs, gamk) = self
    if not prev_inputs.dtype == h.dtype == q_inputs.dtype:
      raise TypeError("Inconsistent internal state: %s vs %s" %
                      (str(prev_inputs.dtype), str(h.dtype), str(q_inputs.dtype)))
    return prev_inputs.dtype


class QuantumFieldCell(RNNCell):
  """Quantum Field recurrent network cell.
  The implementation is based on: Ian Gemp
  """

  def __init__(self, input_size, num_units, fields, gam=0.2, n_inter=0,
               state_is_tuple=True):
    """Initialize the Quantum Field cell.
    Args:
      num_units: int, The number of units in the LSTM cell.
      fields: F(input), functions to compute vector fields.
      state_is_tuple: If True, accepted and returned states are 2-tuples of
        the `prev_state` and `state`.  If False, they are concatenated
        along the column axis.  The latter behavior will soon be deprecated.
    """
    if not state_is_tuple:
      logging.warn("%s: Using a concatenated state is slower and will soon be "
                   "deprecated.  Use state_is_tuple=True.", self)
    self._input_size = input_size
    self._num_units = num_units
    self._fields = fields
    self._gam = gam
    self._n_inter = n_inter
    self._state_is_tuple = state_is_tuple

  @property
  def state_size(self):
    return (QuantumFieldStateTuple(self._input_size, self._num_units, self._input_size, 1)
            if self._state_is_tuple else self._input_size + self._num_units + self._input_size + 1)

  @property
  def output_size(self):
    return self._num_units

  def __call__(self, inputs, state, scope=None):
    """Quantum Field cell."""
    with vs.variable_scope(scope or "quantum_field_cell") as scope:
      if self._state_is_tuple:
        prev_inputs, h, q_inputs, gamk = state
      else:
        prev_inputs = array_ops.slice(state, [0, 0], [-1, self._input_size])
        h = array_ops.slice(state, [0, self._input_size], [-1, self._num_units])
        q_inputs = array_ops.slice(state, [0, self._input_size + self._num_units], [-1, self._input_size])
        gamk = array_ops.slice(state, [0, 2*self._input_size + self._num_units], [-1, 1])

      # Immediate Path Integral: x_{i-1} --> x_{i}
      w = 1.0*0.5*np.cos(np.linspace(0,2*np.pi,num=self._n_inter+2,endpoint=True))
      w = w/np.sum(w)

      trapezoid_fields = w[0]*self._fields(prev_inputs)
      scope.reuse_variables()

      for n in range(1,self._n_inter+1):
        alpha = n/(self._n_inter+1)
        inter = (1-alpha)*prev_inputs + alpha*inputs
        trapezoid_fields += w[n]*self._fields(inter)

      this_fields = self._fields(inputs)
      trapezoid_fields += w[-1]*this_fields

      d_inputs = (inputs - prev_inputs)

      path_int = tf.reduce_sum(tf.mul(trapezoid_fields,d_inputs),reduction_indices=-1)
      path_int = tf.transpose(path_int)

      new_h = path_int + h

      # Quantum Contribution
      # use max trick to force gamk to be effectively zero twice at start
      if self._gam > 0.:
        prev_q_inputs = q_inputs/(gamk+1e-7)

        q_trapezoid_fields = w[0]*self._fields(prev_q_inputs)

        for n in range(1,self._n_inter+1):
          q_alpha = n/(self._n_inter+1)
          q_inter = (1-q_alpha)*prev_q_inputs + q_alpha*inputs
          q_trapezoid_fields += w[n]*self._fields(q_inter)

        q_trapezoid_fields += w[-1]*this_fields

        d_q_inputs = tf.maximum(gamk/self._gam-1,0*gamk)*inputs - q_inputs

        q_path_int = tf.reduce_sum(tf.mul(q_trapezoid_fields,d_q_inputs),reduction_indices=-1)
        q_path_int = tf.transpose(q_path_int)


        # d_q_inputs = tf.maximum(gamk/self._gam-1,0*gamk)*inputs - q_inputs
        # q_path_int = tf.reduce_sum(tf.mul(this_fields,d_q_inputs),reduction_indices=-1)
        # q_path_int = tf.transpose(q_path_int)

        # New h
        new_h += q_path_int

      # New state
      new_q_inputs = self._gam*(q_inputs + prev_inputs)
      new_gamk = self._gam*(gamk+1)

      if self._state_is_tuple:
        new_state = QuantumFieldStateTuple(inputs, new_h, new_q_inputs, new_gamk)
      else:
        new_state = array_ops.concat(1, [inputs, new_h, new_q_inputs, new_gamk])
      
      return new_h, new_state
